"""Offline tests for optional SQS worker orchestration."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import worker
from app.services.document_queue import DocumentQueueUnavailableError


class StopWorker(BaseException):
    """End a mocked worker loop without being caught as a processing failure."""


def make_dependencies() -> dict[str, Mock]:
    return {
        "session_factory": Mock(),
        "provider": Mock(),
        "redis_client": Mock(),
    }


def make_result(value: int) -> worker.ProcessingCycleResult:
    return worker.ProcessingCycleResult(
        chunked_documents=value,
        chunks_created=value * 2,
        embedded_documents=value * 3,
        embedded_chunks=value * 4,
        skipped_chunks=value * 5,
        input_tokens=value * 6,
        embedding_cache_hits=value * 7,
        embedding_cache_misses=value * 8,
        embedding_cache_bypasses=value * 9,
    )


def make_cycle_mocks(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    mocks = SimpleNamespace(
        queue=Mock(return_value=None),
        all_tenants=Mock(return_value=make_result(2)),
        one_tenant=Mock(return_value=make_result(2)),
    )
    monkeypatch.setattr(worker, "process_one_queue_delivery", mocks.queue)
    monkeypatch.setattr(worker, "process_all_tenant_documents", mocks.all_tenants)
    monkeypatch.setattr(worker, "process_one_cycle", mocks.one_tenant)
    return mocks


@pytest.mark.parametrize(
    ("scope", "expected_scope"),
    [(None, None), ("  nimbuscart  ", "nimbuscart")],
)
def test_database_only_cycle_preserves_tenant_scope(
    monkeypatch: pytest.MonkeyPatch,
    scope: str | None,
    expected_scope: str | None,
) -> None:
    mocks = make_cycle_mocks(monkeypatch)
    dependencies = make_dependencies()

    result = worker.process_worker_cycle(**dependencies, tenant_scope=scope)

    mocks.queue.assert_not_called()
    if expected_scope is None:
        mocks.all_tenants.assert_called_once_with(**dependencies)
        mocks.one_tenant.assert_not_called()
        assert result is mocks.all_tenants.return_value
    else:
        mocks.one_tenant.assert_called_once_with(**dependencies, tenant_slug=expected_scope)
        mocks.all_tenants.assert_not_called()
        assert result is mocks.one_tenant.return_value


@pytest.mark.parametrize(
    "queue_result",
    [None, worker.EMPTY_PROCESSING_CYCLE_RESULT, make_result(1)],
)
def test_queue_cycle_runs_database_sweep_and_combines_counters(
    monkeypatch: pytest.MonkeyPatch,
    queue_result: worker.ProcessingCycleResult | None,
) -> None:
    mocks = make_cycle_mocks(monkeypatch)
    mocks.queue.return_value = queue_result
    dependencies = make_dependencies()
    receiver = Mock()
    timeline = Mock()
    timeline.attach_mock(mocks.queue, "queue")
    timeline.attach_mock(mocks.all_tenants, "database")

    result = worker.process_worker_cycle(**dependencies, receiver=receiver)

    assert timeline.mock_calls == [
        call.queue(**dependencies, receiver=receiver),
        call.database(**dependencies),
    ]
    mocks.one_tenant.assert_not_called()
    expected = make_result(3) if queue_result == make_result(1) else make_result(2)
    assert result == expected


@pytest.mark.parametrize(
    "error",
    [
        DocumentQueueUnavailableError("synthetic-private-detail"),
        SQLAlchemyError("synthetic-private-detail"),
    ],
)
def test_expected_queue_failure_keeps_database_polling_and_safe_logs(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    mocks = make_cycle_mocks(monkeypatch)
    mocks.queue.side_effect = error
    warning = Mock()
    monkeypatch.setattr(worker.LOGGER, "warning", warning)
    dependencies = make_dependencies()
    receiver = Mock()

    result = worker.process_worker_cycle(**dependencies, receiver=receiver)

    mocks.queue.assert_called_once_with(**dependencies, receiver=receiver)
    mocks.all_tenants.assert_called_once_with(**dependencies)
    assert result is mocks.all_tenants.return_value
    receiver.ack.assert_not_called()
    warning.assert_called_once_with(
        "Document queue handling did not finish; continuing database polling."
    )


@pytest.mark.parametrize(
    "error",
    [TypeError("synthetic-private-detail"), ValueError("synthetic-private-detail")],
)
def test_malformed_receive_is_not_acknowledged_and_database_sweep_still_runs(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    dependencies = make_dependencies()
    receiver = Mock()
    receiver.receive_one.side_effect = error
    process_next = Mock()
    sweep = Mock(return_value=worker.EMPTY_PROCESSING_CYCLE_RESULT)
    warning = Mock()
    monkeypatch.setattr(worker, "process_next_document", process_next)
    monkeypatch.setattr(worker, "process_all_tenant_documents", sweep)
    monkeypatch.setattr(worker.LOGGER, "warning", warning)

    result = worker.process_worker_cycle(**dependencies, receiver=receiver)

    assert result is worker.EMPTY_PROCESSING_CYCLE_RESULT
    receiver.receive_one.assert_called_once_with()
    receiver.ack.assert_not_called()
    process_next.assert_not_called()
    dependencies["session_factory"].assert_not_called()
    sweep.assert_called_once_with(**dependencies)
    warning.assert_called_once_with(
        "Invalid document queue delivery was rejected without acknowledgment."
    )


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("synthetic-programming-error"),
        ValueError("synthetic-programming-error"),
        TypeError("synthetic-programming-error"),
    ],
)
def test_unexpected_processing_errors_are_not_hidden_by_the_cycle(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    mocks = make_cycle_mocks(monkeypatch)
    mocks.queue.side_effect = error

    with pytest.raises(type(error), match="synthetic-programming-error"):
        worker.process_worker_cycle(**make_dependencies(), receiver=Mock())

    mocks.all_tenants.assert_not_called()


@pytest.mark.parametrize("use_receiver", [False, True])
def test_database_sweep_errors_propagate(
    monkeypatch: pytest.MonkeyPatch,
    use_receiver: bool,
) -> None:
    mocks = make_cycle_mocks(monkeypatch)
    mocks.all_tenants.side_effect = RuntimeError("synthetic-database-error")

    with pytest.raises(RuntimeError, match="synthetic-database-error"):
        worker.process_worker_cycle(
            **make_dependencies(),
            receiver=Mock() if use_receiver else None,
        )


@pytest.mark.parametrize("scope", ["nimbuscart", "  nimbuscart  "])
def test_queue_cycle_rejects_single_tenant_scope_before_processing(
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
) -> None:
    mocks = make_cycle_mocks(monkeypatch)

    with pytest.raises(ValueError, match="unscoped"):
        worker.process_worker_cycle(**make_dependencies(), receiver=Mock(), tenant_scope=scope)

    mocks.queue.assert_not_called()
    mocks.all_tenants.assert_not_called()
    mocks.one_tenant.assert_not_called()


def make_main_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend: str,
    scope: str | None,
) -> SimpleNamespace:
    settings = SimpleNamespace(
        document_queue_backend=backend,
        document_processor_tenant_slug=scope,
        document_processor_poll_interval_seconds=7,
    )
    mocks = SimpleNamespace(
        settings=settings,
        get_settings=Mock(return_value=settings),
        receiver=Mock(),
        session_factory=Mock(),
        redis_client=Mock(),
        provider=Mock(),
        cycle=Mock(return_value=worker.EMPTY_PROCESSING_CYCLE_RESULT),
        sleeper=Mock(side_effect=[None, StopWorker()]),
        aws_session=Mock(),
    )
    mocks.build_receiver = Mock(return_value=mocks.receiver)
    mocks.build_factory = Mock(return_value=mocks.session_factory)
    mocks.build_redis = Mock(return_value=mocks.redis_client)
    mocks.build_provider = Mock(return_value=mocks.provider)
    monkeypatch.setattr(worker, "get_settings", mocks.get_settings)
    monkeypatch.setattr(worker, "build_sqs_document_receiver", mocks.build_receiver)
    monkeypatch.setattr(worker, "get_session_factory", mocks.build_factory)
    monkeypatch.setattr(worker, "get_redis_client", mocks.build_redis)
    monkeypatch.setattr(worker, "build_worker_embedding_provider", mocks.build_provider)
    monkeypatch.setattr(worker, "process_worker_cycle", mocks.cycle)
    monkeypatch.setattr(worker.time, "sleep", mocks.sleeper)
    monkeypatch.setattr("app.infrastructure.sqs.boto3.Session", mocks.aws_session)
    return mocks


@pytest.mark.parametrize(
    ("backend", "scope", "expected_scope"),
    [
        ("disabled", None, None),
        ("disabled", "   ", None),
        ("disabled", "  nimbuscart  ", "nimbuscart"),
        ("sqs", None, None),
        ("sqs", "   ", None),
    ],
)
def test_main_builds_receiver_only_when_enabled_and_reuses_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    scope: str | None,
    expected_scope: str | None,
) -> None:
    mocks = make_main_mocks(monkeypatch, backend=backend, scope=scope)

    with pytest.raises(StopWorker):
        worker.main()

    expected_receiver = mocks.receiver if backend == "sqs" else None
    if backend == "sqs":
        mocks.build_receiver.assert_called_once_with(mocks.settings)
    else:
        mocks.build_receiver.assert_not_called()
    mocks.aws_session.assert_not_called()
    mocks.get_settings.assert_called_once_with()
    mocks.build_factory.assert_called_once_with()
    mocks.build_redis.assert_called_once_with()
    mocks.build_provider.assert_called_once_with(redis_client=mocks.redis_client)
    expected_call = call(
        session_factory=mocks.session_factory,
        provider=mocks.provider,
        redis_client=mocks.redis_client,
        receiver=expected_receiver,
        tenant_scope=expected_scope,
    )
    assert mocks.cycle.call_args_list == [expected_call, expected_call]
    assert mocks.sleeper.call_args_list == [call(7), call(7)]


@pytest.mark.parametrize("scope", ["nimbuscart", "  nimbuscart  "])
def test_main_rejects_sqs_tenant_scope_before_dependency_construction(
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
) -> None:
    mocks = make_main_mocks(monkeypatch, backend="sqs", scope=scope)

    with pytest.raises(ValueError, match="DOCUMENT_PROCESSOR_TENANT_SLUG"):
        worker.main()

    for dependency in (
        mocks.build_receiver,
        mocks.build_factory,
        mocks.build_redis,
        mocks.build_provider,
        mocks.cycle,
        mocks.sleeper,
        mocks.aws_session,
    ):
        dependency.assert_not_called()


def test_main_waits_and_continues_after_a_cycle_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = make_main_mocks(monkeypatch, backend="disabled", scope=None)
    mocks.cycle.side_effect = [
        RuntimeError("synthetic-worker-cycle-error"),
        worker.EMPTY_PROCESSING_CYCLE_RESULT,
    ]
    log_exception = Mock()
    monkeypatch.setattr(worker.LOGGER, "exception", log_exception)

    with pytest.raises(StopWorker):
        worker.main()

    assert mocks.cycle.call_count == 2
    assert mocks.sleeper.call_args_list == [call(7), call(7)]
    log_exception.assert_called_once_with("Document processing cycle failed; it will retry later")
