from __future__ import annotations

import time
from typing import TYPE_CHECKING

from mcpgtw.errors import ChannelCapacityError
from mcpgtw.oauth.consent_policy import ConsentPolicy
from mcpgtw.oauth.verified_principal import VerifiedPrincipal

if TYPE_CHECKING:
    from app.gateway import AppGateway
    from app.session import Session


class GameConsentPolicy(ConsentPolicy):
    def __init__(self, gateway: AppGateway) -> None:
        self.gateway = gateway

    def _session(self, subject: str, resource: str, scopes: frozenset[str]) -> Session | None:
        issuer = self.gateway.settings.oauth_embedded_issuer
        channel_id = self.gateway._oauth_owners.get((issuer, subject))
        session = self.gateway._sessions.get(channel_id)

        if (
            session is None
            or session.oauth_authorized_until <= time.time()
            or resource != self.gateway.settings.oauth_resource_url
            or not scopes <= {"openid", *self.gateway.settings.oauth_supported_scopes}
        ):
            return None

        return session

    async def approve(
        self, subject: str, client_id: str, resource: str, scopes: frozenset[str]
    ) -> bool:
        if resource != self.gateway.settings.oauth_resource_url or not scopes <= {
            "openid",
            *self.gateway.settings.oauth_supported_scopes,
        }:
            return False

        try:
            session = await self.gateway.acquire_oauth_session(
                self.gateway.settings.oauth_embedded_issuer, subject
            )
        except ChannelCapacityError:
            return False

        session.oauth_authorized_until = int(
            time.time() + self.gateway.app_settings.session_idle_seconds
        )
        self.gateway.schedule_idle_teardown(session, self.gateway.app_settings.session_idle_seconds)
        principal = VerifiedPrincipal(
            self.gateway.settings.oauth_embedded_issuer,
            subject,
            client_id,
            scopes,
            session.oauth_authorized_until,
        )
        await self.gateway.channel_grants.grant(principal, session.channel_id)
        return True

    async def validate(
        self, subject: str, client_id: str, resource: str, scopes: frozenset[str]
    ) -> bool:
        session = self._session(subject, resource, scopes)

        if session is None:
            return False

        principal = VerifiedPrincipal(
            self.gateway.settings.oauth_embedded_issuer,
            subject,
            client_id,
            scopes,
            session.oauth_authorized_until,
        )
        return session.channel_id in await self.gateway.channel_grants.channels(principal)

    async def binding(self, subject: str, client_id: str, resource: str) -> str | None:
        return self.gateway._oauth_owners.get(
            (self.gateway.settings.oauth_embedded_issuer, subject)
        )
