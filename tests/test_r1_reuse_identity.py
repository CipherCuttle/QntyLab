from qntylab.r1_reuse_identity import (SEPARATED, UNRESOLVED, announcement_temporal_fields, archive_clusters,
                                       canonical_bytes, classify_lineages, parse_archive_listing, parse_instrument_response)


def test_official_symbol_id_launch_delivery_and_status_filter_are_preserved():
    raw = b'{"result":{"list":[{"symbol":"XUSDT","symbolId":7,"status":"Trading","launchTime":"1","deliveryTime":"0","contractType":"LinearPerpetual","baseCoin":"X","quoteCoin":"USDT"}]}}'
    parsed = parse_instrument_response(raw, "Closed")
    assert parsed["returned_rows"][0]["symbolId"] == 7 and not parsed["status_filter_honored"]


def test_archive_clusters_do_not_prove_relisting_or_terminal():
    assert archive_clusters(["2024-01-01", "2024-01-02", "2024-02-01"]) == [{"start_utc": "2024-01-01", "end_utc": "2024-01-02"}, {"start_utc": "2024-02-01", "end_utc": "2024-02-01"}]
    assert parse_archive_listing(b'<a>TESTUSDT2024-01-01.csv.gz</a>', "TESTUSDT") == ["2024-01-01"]


def test_only_ordered_explicit_event_times_separate_lineages():
    state, intervals, reasons = classify_lineages(exact_terminal_utc="2024-01-01T00:00:00Z", exact_later_launch_utc="2024-02-01T00:00:00Z")
    assert state == SEPARATED and len(intervals) == 3 and not reasons
    state, intervals, reasons = classify_lineages(exact_terminal_utc=None, exact_later_launch_utc="2024-02-01T00:00:00Z")
    assert state == UNRESOLVED and not intervals and reasons == ["no_verified_nonoverlap_boundary"]
    state, _, _ = classify_lineages(exact_terminal_utc="2024-03-01T00:00:00Z", exact_later_launch_utc="2024-02-01T00:00:00Z")
    assert state == UNRESOLVED


def test_announcement_publication_time_is_not_promoted_to_event_time():
    fields = announcement_temporal_fields(None, "2024-01-01T00:00:00Z")
    assert fields["event_time_utc"] is None and fields["publication_time_utc"] == "2024-01-01T00:00:00Z"


def test_same_ticker_does_not_imply_same_instance_and_output_is_canonical():
    state, _, _ = classify_lineages(exact_terminal_utc=None, exact_later_launch_utc=None)
    assert state == UNRESOLVED
    assert canonical_bytes({"b": 1, "a": 2}) == canonical_bytes({"a": 2, "b": 1})
