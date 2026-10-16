import services.flight_service as fs
print("has flight_options_for_package:", hasattr(fs, "flight_options_for_package"))
print("has round_trip_cost:", hasattr(fs, "round_trip_cost"))
print("has flight_summary_for_package:", hasattr(fs, "flight_summary_for_package"))
print("has flight_for_date:", hasattr(fs, "flight_for_date"))
print("__all__:", fs.__all__)