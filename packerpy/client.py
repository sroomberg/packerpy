"""Packer CLI client wrapper."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import IO

from .exceptions import PackerClientError


class PackerClient:
    """Thin wrapper around the HashiCorp Packer CLI.

    Validates that Packer is installed, then provides a ``run`` method to
    execute Packer commands against a given configuration file. Output is
    streamed to the logger and optionally written to log files on disk.

    Args:
        file: Path to the Packer configuration file.
        stream_file_dir: Optional directory to write command log files into.
        log: Optional logger instance. A default logger is created if not provided.
    """

    VALID_COMMANDS = [
        "build",
        "console",
        "fix",
        "fmt",
        "hcl2_upgrade",
        "init",
        "inspect",
        "plugins",
        "validate",
        "versions",
    ]

    def __init__(
        self,
        file: str,
        stream_file_dir: str | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        PackerClient.verify_packer_installation()
        self.file: str = file
        self.stream_file_dir: str | None = stream_file_dir
        self.log: logging.Logger = log or logging.getLogger(PackerClient.__name__)

    def run(self, command: str, *args: str) -> "subprocess.Popen[str]":
        """Execute a Packer CLI command.

        Args:
            command: The Packer sub-command to run (e.g. ``"build"``, ``"validate"``).
            *args: Additional CLI arguments passed before the config file path.

        Returns:
            The completed :class:`subprocess.Popen` handle.

        Raises:
            PackerClientError: If *command* is not a recognised Packer command.
        """
        command = command.strip()
        if command not in self.VALID_COMMANDS:
            raise PackerClientError(f"Invalid command: {command}. Valid commands: {', '.join(self.VALID_COMMANDS)}")
        cmd = [
            "packer",
            command,
            *args,
            self.file,
        ]
        self.log.debug(f"Running command: {', '.join(cmd)}")
        stream_file: IO[str] | None = None
        if self.stream_file_dir:
            os.makedirs(self.stream_file_dir, exist_ok=True)
            stream_file = open(f"{self.stream_file_dir}/packer-{command}.log", "w")
        proc = subprocess.Popen(
            cmd,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        for line in proc.stdout:
            line_str = str(line).strip("\n")
            self.log.info(line_str)
            if stream_file:
                stream_file.write(line_str + "\n")
        if stream_file:
            stream_file.close()
        return proc

    @staticmethod
    def verify_packer_installation() -> None:
        """Check that the ``packer`` binary is available on ``$PATH``.

        Raises:
            EnvironmentError: If Packer is not installed or not on the path.
        """
        try:
            subprocess.check_call(["packer", "version"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise EnvironmentError(
                "Please install packer (https://developer.hashicorp.com/packer/downloads) before using this tool."
            )
