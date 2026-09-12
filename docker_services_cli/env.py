# SPDX-FileCopyrightText: 2020 CERN.
# SPDX-FileCopyrightText: 2024 Graz University of Technology.
# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o.
# SPDX-License-Identifier: MIT

"""Environment module."""

import logging
import os
import sys
from distutils.version import StrictVersion

import click

from .config import SERVICE_TYPES, SERVICES, SERVICES_ALL_DEFAULT_VERSIONS


def normalize_service_name(service_with_version):
    """Return the name of the passed service without version number."""
    service_name = None
    if service_with_version in SERVICES:
        service_name = service_with_version
    else:
        for name in SERVICES:
            if name in service_with_version:
                service_name = name
                break

    return service_name


def _set_default_env(services_version, default_version):
    """Set environmental variable value if it does not exist."""
    os.environ[services_version] = os.environ.get(services_version, default_version)


def _is_version(version):
    """Checks if a string is a version of the format `x.y.z`.

    NOTE: It is not mandatory to be up to patch level. The following would be
    accepted:
    - 10.1
    - 9
    - 15.0.1a2
    """
    try:
        # StrictVersion fails on plain numbers (e.g. "10")
        if version.isnumeric():
            return True
        StrictVersion(version)
        return True
    except Exception:
        return False


def _load_or_set_env(services_version, default_version):
    """Set a specific service version from the environment.

    It parses the value to distinguish between a version and a defined latest.
    NOTE: It requires that all variables for latest versions have been set up.
    """
    version_from_env = os.environ.get(services_version, default_version)
    # e.g. the ES_7_LATEST string from env, need a second get.
    major_version_from_env = os.environ.get(version_from_env)

    if not version_from_env:
        os.environ[services_version] = default_version

    elif _is_version(version_from_env) or version_from_env == "latest":
        os.environ[services_version] = version_from_env

    elif major_version_from_env and (
        _is_version(major_version_from_env) or major_version_from_env == "latest"
    ):
        os.environ[services_version] = major_version_from_env

    else:
        click.secho(
            f"Environment variable for version {version_from_env} not set \
            or set to a non-compliant format (dot separated numbers).",
            fg="red",
        )
        sys.exit(1)


def override_default_env(services_to_override=None):
    """Override default environment according to list of services with version.

    :param services_to_override: List of service name strings including
        service version without any separator e.g. ``postgresql11``.
    """
    services_to_override = set(services_to_override or []).difference(SERVICES.keys())
    if services_to_override:
        num_services_to_override = len(services_to_override)
        for service_name in SERVICES:
            for service_override in services_to_override:
                if service_name in service_override:
                    service_override_version = service_override.replace(
                        service_name, ""
                    )
                    env_var_with_version = (
                        f"{service_name.upper()}_{service_override_version}_LATEST"
                    )
                    if SERVICES_ALL_DEFAULT_VERSIONS.get(env_var_with_version):
                        os.environ[f"{service_name.upper()}_VERSION"] = (
                            SERVICES_ALL_DEFAULT_VERSIONS.get(env_var_with_version)
                        )
                    else:
                        available_major_versions = [
                            v.split(".")[0]
                            for v in SERVICES[service_name]["DEFAULT_VERSIONS"].values()
                        ]
                        click.secho(
                            f"No major version {service_override_version} "
                            f"for {service_name}. "
                            "Please use one of the available "
                            f"ones: {available_major_versions}",
                            fg="red",
                        )
                        exit(1)
                    num_services_to_override -= 1
                    if not num_services_to_override:
                        return


def set_env():
    """Export the environment variables for services and versions."""
    for key, value in SERVICES_ALL_DEFAULT_VERSIONS.items():
        _set_default_env(key, value)

    for service in SERVICES.values():
        for key, value in service.items():
            if key.endswith("_VERSION"):
                _load_or_set_env(key, value)
            elif key == "CONTAINER_CONFIG_ENVIRONMENT_VARIABLES":
                for envvar_name, envvar_value in value.items():
                    _set_default_env(envvar_name, envvar_value)


def print_setup_env_config(services, called_from, env_set_command="export"):
    """Prints setup environment instructions."""
    should_print_instructions = False
    for service_type, services_list in services.items():
        if called_from == "up" and len(services_list) > 1:
            logging.warning(
                "Multiple %s services %s are being configured. "
                "Note that only %s will be accessible.",
                service_type,
                services_list,
                services_list[-1],
            )

        for key, value in get_service_env_vars(service_type, services_list):
            command = f"{env_set_command} {key}"
            if env_set_command == "export":
                command += f"={value}"
            click.echo(command)
            should_print_instructions = True

    if should_print_instructions:
        click.secho("# Configure your environment running:", fg="yellow")
        instructions = f'# eval "$(docker-services-cli {called_from}'
        if called_from == "up" and services != SERVICE_TYPES:
            instructions += " " + " ".join(
                [
                    "--{0} {1}".format(service_type, service)
                    for service_type, services_list in services.items()
                    for service in services_list
                ]
            )
        instructions += ' --env)"'
        click.secho(instructions, fg="yellow")


def get_service_env_vars(service_type, services_list):
    """Get all or a subset of service environment variables."""
    envvars = []
    for service in services_list:
        service_envvars_by_type = (
            SERVICES.get(normalize_service_name(service))
            .get("CONTAINER_CONNECTION_ENVIRONMENT_VARIABLES", {})
            .get(service_type, {})
            .items()
        )
        for key, value in service_envvars_by_type:
            envvars.append((key, value))

    return envvars
