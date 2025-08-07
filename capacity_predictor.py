# Python sınıfının temel OO yapısını oluşturuyoruz.
# Bu sınıf: Bağlantı kurar, veri çeker, Prophet ile eğitir ve metrik bitiş zamanını tahmin eder.
from keystoneauth1 import session
from keystoneauth1.identity import v3
from monascaclient import client
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ResourcePredictor:
    def __init__(self):


        # Gömülü bağlantı bilgileri
        auth_url = "***************************"  # Buraya kendi auth_url'inizi girin
        endpoint = "****************************"  # Buraya kendi endpoint'inizi girin
        project_name = "admin"
        username = "admin"
        password = "***************************"  # Buraya kendi şifrenizi girin
        user_domain_name = "default"
        project_domain_name = "default"

        auth = v3.Password(
            auth_url=auth_url,
            username=username,
            password=password,
            project_name=project_name,
            user_domain_name=user_domain_name,
            project_domain_name=project_domain_name
        )

        sess = session.Session(auth=auth, verify=False)
        self.monasca = client.Client('2_0', session=sess, endpoint=endpoint)


    def _fetch_metric_data(self, host, metric_name):
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        start_time = (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        result = self.monasca.metrics.list_statistics(
            name=metric_name,
            dimensions={"hostname": host},
            start_time=start_time,
            end_time=end_time,
            statistics=['avg'],
            period=86400,
            group_by=['hostname'],
            limit=1000
        )
        return result[0]['statistics']

    def _train_prophet_model(self, statistics):
        import pandas as pd
        from prophet import Prophet
        from datetime import datetime

        # Hazırlık
        timestamps = [datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ") for row in statistics]
        values = [row[1] for row in statistics]

        df = pd.DataFrame({
            "ds": timestamps,
            "y": values
        })

        model = Prophet(daily_seasonality=False)
        model.fit(df)

        future = model.make_future_dataframe(periods=7000)
        forecast = model.predict(future)

        return forecast

    def predict_sufficient_date(self, host, metric_name):
        statistics = self._fetch_metric_data(host, metric_name)
        forecast = self._train_prophet_model(statistics)

        if metric_name == "cpu.percent":
            return self._predict_cpu_exhaustion(forecast)
        elif metric_name == "mem.usable_mb":
            return self._predict_mem_exhaustion(forecast)
        elif metric_name == "disk.total_used_space_mb":
            return self._predict_disk_exhaustion(forecast, host)
        else:
            raise ValueError("Desteklenmeyen metrik")

    def _predict_cpu_exhaustion(self, forecast):
        df = forecast[['ds', 'yhat']]
        threshold = 100
        exceed = df[df['yhat'] >= threshold]
        if not exceed.empty:
            return exceed.iloc[0]['ds']
        return None

    def _predict_mem_exhaustion(self, forecast):
        df = forecast[['ds', 'yhat']]
        below = df[df['yhat'] <= 0]
        if not below.empty:
            return below.iloc[0]['ds']
        return None

    def _predict_disk_exhaustion(self, forecast, host):
        # 1. Kullanılan alanın tahmin sonuçları zaten forecast içinde var
        df = forecast[['ds', 'yhat']]

        # 2. Toplam disk kapasitesini Monasca'dan çek
        total_stat = self._fetch_metric_data(host, "disk.total_space_mb")
        if not total_stat:
            print("Disk toplam kapasitesi alınamadı.")
            return None

        # En güncel değeri al (örneğin en son ölçüm)
        total_disk_capacity_mb = total_stat[-1][1]

        # 3. Tahmin edilen kullanım, toplam kapasiteyi geçtiği an
        exceed = df[df['yhat'] >= total_disk_capacity_mb]
        if not exceed.empty:
            return exceed.iloc[0]['ds']

        return None


    def calculate_daily_growth(self, host, metric_name, target_date):
        import pandas as pd
        from datetime import datetime

        # 1. Tarih formatı kontrolü
        try:
            target = pd.to_datetime(target_date)
        except Exception:
            raise ValueError("Geçersiz tarih formatı. Beklenen: YYYY-MM-DD")

        # 2. Veriyi çek
        statistics = self._fetch_metric_data(host, metric_name)
        timestamps = [datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ") for row in statistics]
        values = [row[1] for row in statistics]

        # 3. DataFrame oluştur
        df = pd.DataFrame({"date": timestamps, "value": values})
        df.set_index("date", inplace=True)

        # 4. Günlük büyüme hesapla
        df['daily_growth'] = df['value'].pct_change(periods=1) * 100
        df.dropna(inplace=True)

        # 5. Tarih geçerli mi?
        if target not in df.index:
            raise ValueError(f"{target_date} tarihli veri bulunamadı. Geçerli tarihler: {df.index.date.min()} → {df.index.date.max()}")

        return round(df.loc[target]['daily_growth'], 2)



    def calculate_weekly_growth(self, host, metric_name, target_date):
        import pandas as pd
        from datetime import datetime

        # 1️⃣ Tarih format kontrolü önce
        try:
            target = pd.to_datetime(target_date)
        except Exception:
            raise ValueError("Geçersiz tarih formatı. Beklenen: YYYY-MM-DD")

        # 2️⃣ Veriyi çek
        statistics = self._fetch_metric_data(host, metric_name)
        timestamps = [datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ") for row in statistics]
        values = [row[1] for row in statistics]

        # 3️⃣ DataFrame hazırla
        df = pd.DataFrame({"date": timestamps, "value": values})
        df.set_index("date", inplace=True)

        # 4️⃣ Haftalık büyüme hesapla
        df['weekly_growth'] = df['value'].pct_change(periods=7) * 100
        df.dropna(inplace=True)

        # 5️⃣ Hedef tarih varsa sonucu dön
        if target not in df.index:
            raise ValueError(
                f"{target_date} tarihli veri bulunamadı. "
                f"Geçerli aralık: {df.index.date.min()} → {df.index.date.max()}"
            )

        return round(df.loc[target]['weekly_growth'], 2)




    def forecast_for_days(self, host, metric_name, days=7):
        statistics = self._fetch_metric_data(host, metric_name)
        if not statistics:
            print(f"{metric_name} verisi alınamadı.")
            return None

        from prophet import Prophet
        from datetime import datetime
        import pandas as pd

        timestamps = [datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ") for row in statistics]
        values = [row[1] for row in statistics]
        df = pd.DataFrame({"ds": timestamps, "y": values})

        model = Prophet(daily_seasonality=False)
        model.fit(df)

        future = model.make_future_dataframe(periods=days)
        forecast = model.predict(future)

        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days)
