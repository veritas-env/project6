"""A06 Insecure Design: TravelEase booking and loyalty rules."""

from __future__ import annotations

from tests.conftest import points


def book(w, who="alice", flight=None, passengers=1):
    return getattr(w, who).client.post("/api/v1/bookings", json={
        "flight_id": str(flight or w.ids["flight2"]), "passengers": passengers, "contact_email": f"{who}@lab.test"})


def test_booking_awards_points_by_fare(app, world):
    before = points(world)
    r = book(world, flight=world.ids["flight2"])  # £80 fare -> 80 points
    assert r.status_code == 201 and r.json()["points_earned"] == 80
    assert points(world) == before + 80


def test_booking_reserves_seats(app, world):
    f = world.alice.client.get("/api/v1/flights").json()
    seats = next(x for x in f if x["id"] == str(world.ids["flight2"]))["seats_available"]
    book(world, flight=world.ids["flight2"], passengers=3)
    f2 = world.alice.client.get("/api/v1/flights").json()
    assert next(x for x in f2 if x["id"] == str(world.ids["flight2"]))["seats_available"] == seats - 3


def test_cannot_overbook(app, world):
    # flight2 has 180 seats; booking 9 at a time, eventually full
    for _ in range(20):
        book(world, flight=world.ids["flight2"], passengers=9)
    r = book(world, flight=world.ids["flight2"], passengers=9)
    assert r.status_code == 409 and r.json()["error"] == "not_enough_seats"


def test_cancel_releases_seats(app, world):
    r = book(world, flight=world.ids["flight2"], passengers=2)
    bid = r.json()["id"]
    f = world.alice.client.get("/api/v1/flights").json()
    seats = next(x for x in f if x["id"] == str(world.ids["flight2"]))["seats_available"]
    assert world.alice.client.post(f"/api/v1/bookings/{bid}/cancel").status_code == 200
    f2 = world.alice.client.get("/api/v1/flights").json()
    assert next(x for x in f2 if x["id"] == str(world.ids["flight2"]))["seats_available"] == seats + 2


def test_cannot_cancel_twice(app, world):
    r = book(world, flight=world.ids["flight2"])
    bid = r.json()["id"]
    assert world.alice.client.post(f"/api/v1/bookings/{bid}/cancel").status_code == 200
    assert world.alice.client.post(f"/api/v1/bookings/{bid}/cancel").status_code == 409


def test_passenger_count_bounded(app, world):
    assert book(world, flight=world.ids["flight2"], passengers=0).status_code == 422
    assert book(world, flight=world.ids["flight2"], passengers=10).status_code == 422


def test_limits(app, world):
    assert world.alice.client.get("/api/v1/bookings", params={"limit": 10_000}).status_code == 422
    assert world.alice.client.get("/api/v1/flights", params={"origin": "TOOLONG"}).status_code == 422
