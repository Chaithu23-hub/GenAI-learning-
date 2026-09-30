import pytest

from legal_rag.infrastructure.observability.metrics import (
    Counter,
    Histogram,
    MetricsRegistry,
    reset_metrics,
)


@pytest.fixture(autouse=True)
def _fresh_metrics():
    reset_metrics()
    yield
    reset_metrics()


class TestCounter:
    def test_increment_and_render(self):
        c = Counter("hits_total", "hit counter")
        c.inc()
        c.inc(2, kind="ok")
        text = c.render()
        assert "hits_total 1" in text
        assert 'hits_total{kind="ok"} 2' in text

    def test_no_data_still_renders_zero(self):
        assert "hits_total 0" in Counter("hits_total", "h").render()

    def test_labels_are_escaped(self):
        c = Counter("m", "help")
        c.inc(kind='ok"; drop table --')
        assert "\\\"" in c.render()


class TestHistogram:
    def test_observe_and_render(self):
        h = Histogram("d_seconds", "d", buckets=(0.1, 0.5))
        h.observe(0.05)
        h.observe(0.4)
        h.observe(0.6)
        text = h.render()
        assert "d_seconds_count 3" in text
        assert 'd_seconds_bucket{le="0.1"} 1' in text
        assert 'd_seconds_bucket{le="0.5"} 2' in text
        assert 'd_seconds_bucket{le="+Inf"} 3' in text

    def test_time_context_manager_records_positive(self):
        h = Histogram("d_seconds", "d", buckets=(0.001,))
        with h.time():
            pass
        text = h.render()
        assert "d_seconds_count 1" in text


class TestRegistryEndToEnd:
    def test_prometheus_format_is_syntactically_valid(self):
        reg = MetricsRegistry()
        reg.requests.inc(outcome="answered")
        reg.request_duration.observe(0.123, outcome="answered")
        text = reg.render_prometheus()
        # Every metric block must open with HELP + TYPE.
        assert text.count("# HELP ") >= 5
        assert text.count("# TYPE ") >= 5
        assert text.endswith("\n")
