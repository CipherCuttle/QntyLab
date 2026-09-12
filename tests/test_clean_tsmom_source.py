from datetime import UTC, datetime
from qntylab.clean_tsmom_source import archive_url, month_starts, parse_zip_rows
import io, zipfile

def test_month_boundary_and_exclusive_end():
    assert month_starts(datetime(2026,3,1,tzinfo=UTC), datetime(2026,8,1,tzinfo=UTC)) == [(2026,3),(2026,4),(2026,5),(2026,6),(2026,7)]

def test_funding_archive_path_and_no_premium_requirement():
    assert archive_url('fundingRate','BTCUSDT',2026,6).endswith('/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-06.zip')
    assert 'premiumIndexKlines' not in archive_url('klines','BTCUSDT',2026,6)

def test_header_and_no_header_zip_rows():
    for body in (b'timestamp,open,high,low,close,volume\n1,1,1,1,1,1\n', b'1,1,1,1,1,1\n'):
        stream=io.BytesIO(); z=zipfile.ZipFile(stream,'w'); z.writestr('BTCUSDT-1h-2026-06.csv',body); z.close()
        rows,names=parse_zip_rows(stream.getvalue(),expected_symbol='BTCUSDT',expected_kind='klines')
        assert len(rows)==1 and names==['BTCUSDT-1h-2026-06.csv']
