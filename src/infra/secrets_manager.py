"""Abstraction de gestion des secrets (MLOPS-118).

Une interface unique ``SecretsManager`` avec trois implémentations :
  - ``EnvSecretsManager``   : variables d'environnement (dev, défaut).
  - ``VaultSecretsManager`` : HashiCorp Vault (via python-hvac).
  - ``AWSSecretsManager``   : AWS Secrets Manager (via boto3).

Sélection via ``SECRETS_BACKEND`` (``env`` | ``vault`` | ``aws``). hvac et boto3
sont importés paresseusement → aucune dépendance dure si le backend n'est pas
utilisé. Le code applicatif ne lit jamais un secret en dur : il passe par
``get_secrets_manager().get_secret("JWT_SECRET")``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod


class SecretsManager(ABC):
    @abstractmethod
    def get_secret(self, key: str) -> str | None:
        """Retourne la valeur du secret ``key`` (ou None s'il est absent)."""

    def rotate_secret(self, key: str, new_value: str) -> bool:
        """Met à jour/rote le secret. Par défaut non supporté."""
        raise NotImplementedError


class EnvSecretsManager(SecretsManager):
    """Dev : lit (et « rote ») les secrets depuis l'environnement du process."""

    def get_secret(self, key: str) -> str | None:
        return os.environ.get(key)

    def rotate_secret(self, key: str, new_value: str) -> bool:
        os.environ[key] = new_value
        return True


class VaultSecretsManager(SecretsManager):
    """HashiCorp Vault (KV v2). Secrets stockés sous ``<mount>/<base>/<key>``."""

    def __init__(self, url: str, token: str, mount: str = "secret", base: str = "rag"):
        import hvac  # import paresseux

        self.client = hvac.Client(url=url, token=token)
        self.mount = mount
        self.base = base

    def get_secret(self, key: str) -> str | None:
        resp = self.client.secrets.kv.v2.read_secret_version(
            path=f"{self.base}/{key}", mount_point=self.mount
        )
        return resp["data"]["data"].get("value")

    def rotate_secret(self, key: str, new_value: str) -> bool:
        self.client.secrets.kv.v2.create_or_update_secret(
            path=f"{self.base}/{key}",
            secret={"value": new_value},
            mount_point=self.mount,
        )
        return True


class AWSSecretsManager(SecretsManager):
    """AWS Secrets Manager. Secrets nommés ``<base>/<key>``."""

    def __init__(self, region: str = "us-east-1", base: str = "rag"):
        import boto3  # import paresseux

        self.client = boto3.client("secretsmanager", region_name=region)
        self.base = base

    def get_secret(self, key: str) -> str | None:
        resp = self.client.get_secret_value(SecretId=f"{self.base}/{key}")
        return resp.get("SecretString")

    def rotate_secret(self, key: str, new_value: str) -> bool:
        self.client.put_secret_value(
            SecretId=f"{self.base}/{key}", SecretString=new_value
        )
        return True


def get_secrets_manager(backend: str | None = None) -> SecretsManager:
    """Fabrique le gestionnaire selon ``SECRETS_BACKEND`` (défaut : env)."""
    backend = (backend or os.environ.get("SECRETS_BACKEND", "env")).lower()
    if backend == "vault":
        return VaultSecretsManager(
            url=os.environ["VAULT_ADDR"], token=os.environ["VAULT_TOKEN"]
        )
    if backend == "aws":
        return AWSSecretsManager(region=os.environ.get("AWS_REGION", "us-east-1"))
    return EnvSecretsManager()
