import inspect

from faultwitness_dev.runtime_deploy import deploy_runtime_schema, inspect_runtime_schema


def test_runtime_deploy_uses_content_provenance_without_binding_or_timeout() -> None:
    deploy_source = inspect.getsource(deploy_runtime_schema)
    inspect_source = inspect.getsource(inspect_runtime_schema)
    assert "producer_provenance" in deploy_source
    assert "candidate-binding" not in deploy_source + inspect_source
    assert "timeout=" not in deploy_source + inspect_source
