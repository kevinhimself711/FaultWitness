"""Authenticated identity derived from OIDC claims only."""

from .oidc import AuthenticatedPrincipal, OIDCAuthenticator, OIDCSettings

__all__ = ["AuthenticatedPrincipal", "OIDCAuthenticator", "OIDCSettings"]
