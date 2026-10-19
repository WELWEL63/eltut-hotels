# ElTut Tours Platform — Full Code & Status Report
**Generated:** 2026-10-19 00:19:45

## 1. Database Schema & Row Counts
| Table | Row Count |
|-------|-----------|
| activities | 177 |
| activity_exclusions | 531 |
| activity_faqs | 885 |
| activity_images | 1107 |
| activity_inclusions | 708 |
| activity_languages | 1062 |
| activity_prices | 177 |
| activity_tips | 708 |
| airlines | 4 |
| airports | 24 |
| alembic_version | 1 |
| booking_items | 80 |
| booking_rooms | 22 |
| booking_status_history | 48 |
| booking_travellers | 95 |
| bookings | 38 |
| destinations | 16 |
| flight_prices | 458 |
| flights | 21 |
| guides | 1 |
| home_offers | 18 |
| hotel_exclusions | 900 |
| hotel_facilities | 7740 |
| hotel_faqs | 540 |
| hotel_images | 191 |
| hotel_inclusions | 900 |
| hotel_tips | 840 |
| hotels | 180 |
| newsletters | 0 |
| package_exclusions | 90 |
| package_faqs | 90 |
| package_flights | 156 |
| package_images | 25 |
| package_inclusions | 121 |
| package_itineraries | 126 |
| package_options | 45 |
| package_prices | 2862 |
| package_tips | 72 |
| packages | 20 |
| payments | 38 |
| quotes | 5 |
| room_images | 0 |
| room_rates | 4454 |
| rooms | 632 |
| site_content | 172 |
| suppliers | 3 |
| users | 3 |

## 2. Business Stats
- Total Bookings: **38**
- Total Revenue: **GBP 28,050.59**
- Flight Links (PackageFlight): **156**

## 3. All Registered Routes
| Method | Route | Endpoint |
|--------|-------|----------|
| GET | / | public.index |
| GET | /_health | _health |
| GET | /about | public.about |
| GET | /account/ | account.index |
| GET | /account/bookings | account.bookings |
| GET | /account/bookings/<reference> | account.booking_detail |
| POST | /account/bookings/<reference>/cancel | account.booking_cancel |
| GET,POST | /account/profile | account.profile |
| GET | /activities | public.activity_list |
| GET | /activities/<slug> | public.activity_detail |
| GET | /admin/ | admin.index |
| GET | /admin/activities | admin.activity_list |
| POST | /admin/activities/<int:activity_id>/children/<child_type>/<int:row_id>/delete | admin.activity_child_delete |
| POST | /admin/activities/<int:activity_id>/children/<child_type>/new | admin.activity_child_new |
| POST | /admin/activities/<int:activity_id>/delete | admin.activity_delete |
| GET,POST | /admin/activities/<int:activity_id>/edit | admin.activity_edit |
| POST | /admin/activities/<int:activity_id>/toggle | admin.activity_toggle |
| GET,POST | /admin/activities/new | admin.activity_new |
| GET | /admin/airlines | admin.airline_list |
| POST | /admin/airlines/<int:airline_id>/delete | admin.airline_delete |
| GET,POST | /admin/airlines/<int:airline_id>/edit | admin.airline_edit |
| POST | /admin/airlines/<int:airline_id>/logo | admin.airline_logo_upload |
| POST | /admin/airlines/<int:airline_id>/logo/delete | admin.airline_logo_delete |
| POST | /admin/airlines/<int:airline_id>/toggle | admin.airline_toggle |
| GET,POST | /admin/airlines/new | admin.airline_new |
| GET | /admin/api/packages/rooms-for-hotel/<int:hotel_id> | admin.api_rooms_for_hotel |
| GET | /admin/bookings | admin.booking_list |
| GET | /admin/bookings/<reference> | admin.booking_detail |
| POST | /admin/bookings/<reference>/cancel | admin.booking_cancel |
| POST | /admin/bookings/<reference>/status | admin.booking_status |
| GET | /admin/content | admin.content_index |
| GET,POST | /admin/content/edit/<path:key> | admin.content_edit |
| POST | /admin/content/reset/<path:key> | admin.content_reset |
| POST | /admin/content/seed | admin.content_seed |
| GET | /admin/content/slideshow | admin.content_slideshow |
| POST | /admin/content/slideshow/<int:slot>/delete | admin.content_slideshow_delete |
| POST | /admin/content/slideshow/<int:slot>/save | admin.content_slideshow_save |
| POST | /admin/content/slideshow/<int:slot>/update-url | admin.content_slideshow_update_url |
| POST | /admin/content/slideshow/<int:slot>/upload | admin.content_slideshow_upload |
| POST | /admin/destinations/<int:dest_id>/image/delete | admin.destination_image_delete |
| POST | /admin/destinations/<int:dest_id>/image/upload | admin.destination_image_upload |
| GET | /admin/destinations/images | admin.destination_images |
| GET | /admin/enquiries | admin.enquiry_list |
| POST | /admin/enquiries/<enquiry_id>/status | admin.enquiry_status |
| POST | /admin/exclusions/<int:exclusion_id>/delete | admin.package_exclusion_delete |
| GET | /admin/flights | admin.flight_admin_index |
| POST | /admin/flights/<int:flight_id>/delete | admin.package_flight_delete |
| POST | /admin/flights/<int:fp_id>/delete | admin.flight_admin_delete |
| POST | /admin/flights/delete-all | admin.flight_admin_delete_all |
| GET | /admin/flights/export | admin.flight_admin_export |
| GET,POST | /admin/flights/import | admin.flight_admin_import |
| GET | /admin/hotel-csv | admin.hotel_csv_index |
| GET | /admin/hotel-csv/export | admin.hotel_csv_export |
| GET,POST | /admin/hotel-csv/import | admin.hotel_csv_import |
| POST | /admin/hotel-facilities/<int:facility_id>/delete | admin.hotel_facility_delete |
| GET | /admin/hotels | admin.hotel_list |
| POST | /admin/hotels/<int:hotel_id>/children/<child_type>/<int:row_id>/delete | admin.hotel_child_delete |
| POST | /admin/hotels/<int:hotel_id>/children/<child_type>/new | admin.hotel_child_new |
| POST | /admin/hotels/<int:hotel_id>/delete | admin.hotel_delete |
| GET,POST | /admin/hotels/<int:hotel_id>/edit | admin.hotel_edit |
| POST | /admin/hotels/<int:hotel_id>/facilities/new | admin.hotel_facility_new |
| POST | /admin/hotels/<int:hotel_id>/rooms/new | admin.room_new |
| POST | /admin/hotels/<int:hotel_id>/toggle | admin.hotel_toggle |
| GET,POST | /admin/hotels/new | admin.hotel_new |
| POST | /admin/inclusions/<int:inclusion_id>/delete | admin.package_inclusion_delete |
| POST | /admin/itinerary/<int:itinerary_id>/delete | admin.package_itinerary_delete |
| GET | /admin/media | admin.media_index |
| POST | /admin/media/<product_type>/<int:image_id>/delete | admin.media_delete |
| POST | /admin/media/<product_type>/<int:image_id>/reorder | admin.media_reorder |
| GET | /admin/media/product/<product_type>/<int:parent_id> | admin.media_for_product |
| POST | /admin/media/product/<product_type>/<int:parent_id>/upload | admin.media_upload |
| GET | /admin/offers | admin.offers_index |
| POST | /admin/offers/<int:offer_id>/move | admin.offers_move |
| POST | /admin/offers/<int:offer_id>/remove | admin.offers_remove |
| POST | /admin/offers/<int:offer_id>/toggle | admin.offers_toggle |
| POST | /admin/offers/<section>/add | admin.offers_add |
| GET | /admin/offers/<section>/search | admin.offers_search |
| POST | /admin/options/<int:option_id>/delete | admin.package_option_delete |
| POST | /admin/package-flight-cards/<int:card_id>/delete | admin.package_flight_card_delete |
| POST | /admin/package-flight-cards/<int:card_id>/toggle | admin.package_flight_card_toggle |
| POST | /admin/package-prices/<int:price_id>/delete | admin.package_price_delete |
| GET | /admin/packages | admin.package_list |
| POST | /admin/packages/<int:package_id>/children/<child_type>/<int:row_id>/delete | admin.package_child_delete |
| POST | /admin/packages/<int:package_id>/children/<child_type>/new | admin.package_child_new |
| POST | /admin/packages/<int:package_id>/delete | admin.package_delete |
| GET,POST | /admin/packages/<int:package_id>/edit | admin.package_edit |
| POST | /admin/packages/<int:package_id>/exclusions/new | admin.package_exclusion_new |
| POST | /admin/packages/<int:package_id>/flight-cards/new | admin.package_flight_card_new |
| POST | /admin/packages/<int:package_id>/flights/new | admin.package_flight_new |
| POST | /admin/packages/<int:package_id>/inclusions/new | admin.package_inclusion_new |
| POST | /admin/packages/<int:package_id>/itinerary/new | admin.package_itinerary_new |
| POST | /admin/packages/<int:package_id>/options/<int:option_id>/update | admin.package_option_update |
| POST | /admin/packages/<int:package_id>/options/new | admin.package_option_new |
| POST | /admin/packages/<int:package_id>/prices/new | admin.package_price_new |
| POST | /admin/packages/<int:package_id>/toggle | admin.package_toggle |
| GET,POST | /admin/packages/new | admin.package_new |
| GET | /admin/quotes | admin.quote_list |
| GET,POST | /admin/quotes/<reference> | admin.quote_detail |
| POST | /admin/quotes/<reference>/cancel | admin.quote_cancel |
| POST | /admin/quotes/<reference>/send | admin.quote_send |
| GET,POST | /admin/quotes/new | admin.quote_new |
| GET | /admin/quotes/requests | admin.quote_requests |
| GET | /admin/reports | admin.report_index |
| GET | /admin/reports/export | admin.report_export |
| GET | /admin/reviews | admin.review_list |
| POST | /admin/reviews/<review_id>/delete | admin.review_delete |
| POST | /admin/room-rates/<int:rate_id>/delete | admin.room_rate_delete |
| POST | /admin/room-rates/<int:rate_id>/edit | admin.room_rate_edit |
| POST | /admin/rooms/<int:room_id>/delete | admin.room_delete |
| GET,POST | /admin/rooms/<int:room_id>/edit | admin.room_edit |
| POST | /admin/rooms/<int:room_id>/rates/new | admin.room_rate_new |
| GET | /admin/users | admin.user_list |
| GET | /admin/users/<int:id> | admin.user_detail |
| POST | /admin/users/<int:id>/role | admin.user_role |
| POST | /admin/users/<int:id>/toggle | admin.user_toggle |
| GET | /api/v1/_health | api.api_health |
| GET | /api/v1/activities | api.activities_list |
| GET | /api/v1/activities/<identifier> | api.activities_detail |
| POST | /api/v1/bookings | api.bookings_create |
| GET | /api/v1/bookings/<reference> | api.bookings_detail |
| GET | /api/v1/hotels | api.hotels_list |
| GET | /api/v1/hotels/<identifier> | api.hotels_detail |
| GET | /api/v1/packages | api.packages_list |
| GET | /api/v1/packages/<identifier> | api.packages_detail |
| POST | /api/v1/payments/capture-order | api.payments_capture_order |
| POST | /api/v1/payments/create-order | api.payments_create_order |
| POST | /api/v1/payments/paypal/webhook | api.payments_paypal_webhook |
| GET | /booking/confirmation/<reference> | public.booking_confirmation |
| POST | /booking/create | public.booking_create |
| GET | /booking/paypal/cancel | public.booking_paypal_cancel |
| GET | /booking/paypal/return | public.booking_paypal_return |
| GET | /booking/start/<product_type>/<int:product_id> | public.booking_start |
| GET | /contact | public.contact |
| POST | /enquiries | public.enquiry_submit |
| GET | /enquiries/new | public.enquiry_form |
| GET,POST | /forgot-password | auth.forgot_password |
| GET | /hotels | public.hotel_list |
| GET | /hotels/<slug> | public.hotel_detail |
| GET,POST | /login | auth.login |
| POST | /logout | auth.logout |
| GET | /packages | public.package_list |
| GET | /packages/<slug> | public.package_detail |
| GET | /quote/<reference> | public.quote_view |
| POST | /quote/<reference>/accept | public.quote_accept |
| POST | /quote/<reference>/decline | public.quote_decline |
| GET,POST | /quote/request | public.quote_request |
| GET | /quote/request/thanks | public.quote_request_thanks |
| GET,POST | /register | auth.register |
| GET,POST | /reset-password/<token> | auth.reset_password |
| POST | /reviews/submit | public.review_submit |
| GET | /search | public.search_shortcut |
| GET | /search/results | public.search_results |
| GET | /verify-email/<token> | auth.verify_email |

## 4. Project File Inventory
### models/ (29 files)
- /models/__init__.py
- /models/activity.py
- /models/activity_children.py
- /models/airline.py
- /models/airport.py
- /models/booking.py
- /models/booking_item.py
- /models/booking_room.py
- /models/booking_status_history.py
- /models/booking_traveller.py
- /models/destination.py
- /models/flight.py
- /models/flight_price.py
- /models/guide.py
- /models/home_offer.py
- /models/hotel.py
- /models/hotel_children.py
- /models/newsletter.py
- /models/package.py
- /models/package_children.py
- ...and 9 more files.

### services/ (20 files)
- /services/__init__.py
- /services/auth_service.py
- /services/availability_service.py
- /services/booking_service.py
- /services/content_service.py
- /services/email_service.py
- /services/flight_csv_service.py
- /services/flight_import_service.py
- /services/flight_service.py
- /services/hotel_capacity_service.py
- /services/hotel_csv_service.py
- /services/hotel_pricing_service.py
- /services/package_options_service.py
- /services/package_pricing_service.py
- /services/payment_service.py
- /services/pricing_service.py
- /services/quote_service.py
- /services/recommendation_service.py
- /services/report_service.py
- /services/search_service.py

### blueprints/ (42 files)
- /blueprints/__init__.py
- /blueprints/account/__init__.py
- /blueprints/account/forms.py
- /blueprints/account/routes.py
- /blueprints/admin/__init__.py
- /blueprints/admin/activity_admin.py
- /blueprints/admin/airline_admin.py
- /blueprints/admin/booking_admin.py
- /blueprints/admin/content_admin.py
- /blueprints/admin/destination_admin.py
- /blueprints/admin/flight_admin.py
- /blueprints/admin/hotel_admin.py
- /blueprints/admin/hotel_csv_admin.py
- /blueprints/admin/media_routes.py
- /blueprints/admin/offer_admin.py
- /blueprints/admin/package_admin.py
- /blueprints/admin/quote_admin.py
- /blueprints/admin/report_routes.py
- /blueprints/admin/review_admin.py
- /blueprints/admin/routes.py
- ...and 22 more files.

### scripts/ (30 files)
- /scripts/__init__.py
- /scripts/apply_flight_links.py
- /scripts/auto_link_packages.py
- /scripts/auto_match_all_flights.py
- /scripts/backfill_airport_codes.py
- /scripts/backfill_hotel_slugs.py
- /scripts/cleanup_legacy_flights.py
- /scripts/consolidate_packages.py
- /scripts/create_admin.py
- /scripts/enrich_activity_faqs_tips.py
- /scripts/enrich_activity_maps.py
- /scripts/enrich_hotels.py
- /scripts/enrich_package_faqs_tips.py
- /scripts/fix_options.py
- /scripts/flight_formats/__init__.py
- /scripts/flight_formats/_date_format.py
- /scripts/flight_formats/easyjet_to_canonical.py
- /scripts/flight_formats/jet2_to_canonical.py
- /scripts/generate_report.py
- /scripts/health_check.py
- ...and 10 more files.

### templates/ (65 files)
- /templates/account/booking_detail.html
- /templates/account/bookings.html
- /templates/account/index.html
- /templates/account/profile.html
- /templates/admin/activity_form.html
- /templates/admin/activity_list.html
- /templates/admin/airline_form.html
- /templates/admin/airline_list.html
- /templates/admin/base.html
- /templates/admin/booking_detail.html
- /templates/admin/booking_list.html
- /templates/admin/content_edit.html
- /templates/admin/content_index.html
- /templates/admin/content_slideshow.html
- /templates/admin/destination_images.html
- /templates/admin/enquiry_list.html
- /templates/admin/flight_admin.html
- /templates/admin/flight_import.html
- /templates/admin/hotel_csv.html
- /templates/admin/hotel_csv_import.html
- ...and 45 more files.

### static/css/ (2 files)
- /static/css/eltut.css
- /static/css/search_results.css

## 5. Automation Scripts
- scripts/__init__.py
- scripts/apply_flight_links.py
- scripts/auto_link_packages.py
- scripts/auto_match_all_flights.py
- scripts/backfill_airport_codes.py
- scripts/backfill_hotel_slugs.py
- scripts/cleanup_legacy_flights.py
- scripts/consolidate_packages.py
- scripts/create_admin.py
- scripts/enrich_activity_faqs_tips.py
- scripts/enrich_activity_maps.py
- scripts/enrich_hotels.py
- scripts/enrich_package_faqs_tips.py
- scripts/fix_options.py
- scripts/generate_report.py
- scripts/health_check.py
- scripts/import_trip_images.py
- scripts/reset_db.py
- scripts/seed_airports.py
- scripts/seed_cms_flights_max.py
- scripts/seed_cover_images.py
- scripts/seed_from_csv.py
- scripts/seed_package_details.py
- scripts/session_report.py
- scripts/set_destination_bookable.py
- scripts/test_flights.py

## 6. Environment Configuration
- FLASK_ENV: development
- Database: PostgreSQL (Neon)
- MongoDB: Connected
- PayPal: Configured

## 7. Known Issues & Next Steps
- Empty packages/rooms (£0.00) - Fix via Admin.
- Missing images in static/images/ (PayPal, Mastercard, etc.).
- Cloud Function (worker.py) not yet wired to email notifications.
- ooking_confirmation.html div imbalance (minor CSS fix).

## 8. Security Checklist
- [x] Debug mode OFF
- [x] SECRET_KEY rotated
- [x] CSRF Protection enabled
- [x] Security Headers (CSP, HSTS, X-Frame)
- [x] IDOR prevention on account routes
- [x] BOM removed from 76 files
- [ ] Missing images (/static/images/payments/*)
