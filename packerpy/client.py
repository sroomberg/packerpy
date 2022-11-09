import logging
import os
import subprocess

from .exceptions import PackerClientError


class PackerClient:
    def __init__(self, file, stream_file_dir=None, log=None):
        PackerClient.verify_packer_installation()
        self.file = file
        self.stream_file_dir = stream_file_dir
        self.log = log or logging.getLogger(PackerClient.__name__)

    def run(self, command, *args):
        valid_commands = [
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
        command = command.strip()
        if command not in valid_commands:
            raise PackerClientError(f"Invalid command: {command}. Valid commands: {', '.join(valid_commands)}")
        cmd = [
            "packer",
            command,
            *args,
            self.file,
        ]
        self.log.debug(f"Running command: {', '.join(cmd)}")
        if self.stream_file_dir:
            os.makedirs(self.stream_file_dir, exist_ok=True)
            stream_file = open(f"{self.stream_file_dir}/packer-{command}.log", "w")
        else:
            stream_file = None
        proc = subprocess.Popen(
            command,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        for line in proc.stdout:
            line_str = str(line).strip("\n")
            print(line_str) if not self.log else self.log.info(line_str)
        if stream_file:
            stream_file.write(proc.stdout.read())
            stream_file.close()
        return proc

    @staticmethod
    def verify_packer_installation():
        try:
            subprocess.check_call("packer version")
        except subprocess.CalledProcessError:
            raise EnvironmentError("Please install packer (https://developer.hashicorp.com/packer/downloads) before using this tool.")
