class GovernanceError(RuntimeError):
    """Raised when a repository governance invariant is violated."""


class InfrastructureFailure(GovernanceError):
    """Raised when an external operation produced no evaluable observation."""
