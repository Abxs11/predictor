from capacity_predictor import ResourcePredictor

# 🔧 ÖRNEK KULLANIM
if __name__ == "__main__":
    predictor = ResourcePredictor()

    host = "test-infra02"
    metric = "cpu.percent"  # Diğerleri: "mem.usable_mb", "disk.total_used_space_mb"
    target_date = "2025-07-10"#YYYY MM DD
    tahmin_df = predictor.forecast_for_days(host, metric, days=7000)
    print(tahmin_df)    
    date = predictor.predict_sufficient_date(host, metric)

    if date:
        print(f"\n '{metric}' için yetersizlik tahmini: {date.strftime('%Y-%m-%d')}")
    else:
       print(f"\n '{metric}' için tahmin yapılamadı.")
    

    daily = predictor.calculate_daily_growth(host, metric, target_date)
    weekly = predictor.calculate_weekly_growth(host, metric, target_date)

    print(f" {date} için:")
    print(f" Günlük Büyüme: %{daily}")
    print(f" Haftalık Büyüme: %{weekly}")
