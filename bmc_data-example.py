import os
import subprocess
import json
import logging
import hvac

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def call_cmd(cmd, output_json=True):
    """Run a command and return the output.

    :param cmd: command to run
    :param output_json: output the result as JSON
    :return: subprocess stdout
    :raises RuntimeError: on subprocess non-zero return code
    """
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        logger.error(error)

    if proc.stdout:
        output = proc.stdout.decode()

        if output_json:
            return json.loads(output)

        return output


def get_bmc_info(maas_user, node_id):
    """Fetch BMC information from a given node.

    :param maas_user: User of the MAAS system
    :param node_id: ID of the node
    :return: Tuple containing BMC IP, User, and Password
    """
    logger.info(f"Fetching BMC information from node {node_id}")
    data = call_cmd(["maas", maas_user, "node", "power-parameters", node_id])
    bmc_ip = data["power_address"]
    bmc_user = data["power_user"]
    bmc_pass = data["power_pass"]

    return bmc_ip, bmc_user, bmc_pass


def set_environ_vars(bmc_ip, bmc_user, bmc_pass):
    os.environ["BMC_IP"] = bmc_ip
    os.environ["BMC_USER"] = bmc_user
    os.environ["BMC_PASS"] = bmc_pass


def main():
    maas_user = "testflinger_a"
    node_id = "m7gfpp"
    vault_url = "http://172.16.0.2:8200"
    vault_token = "nh-vault-root"

    bmc_ip, bmc_user, bmc_pass = get_bmc_info(maas_user, node_id)
    set_environ_vars(bmc_ip, bmc_user, bmc_pass)

    client = hvac.Client(
        url=vault_url, token=vault_token
    )

    secret_path = f"bmc-{node_id}"
    client.secrets.kv.v2.create_or_update_secret(
        path=secret_path,
        secret=dict(
            ip=bmc_ip, user=bmc_user, passw=bmc_pass
        ),
    )

    read_response = client.secrets.kv.read_secret_version(path=secret_path)
    # vault secret dic path is ['data']['data'][key]
    logger.info("Read BMC Info from Vault: %s", read_response['data']['data'])


if __name__ == "__main__":
    main()
