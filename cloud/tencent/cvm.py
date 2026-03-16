"""腾讯云 CVM — 云服务器管理。

SDK: tencentcloud-sdk-python-cvm
"""

import json
import logging
import secrets
import string

from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.cvm.v20170312 import cvm_client, models

from cloud.tencent.client import get_tc_credential
from config import settings

logger = logging.getLogger(__name__)

SPEC_MAP = {
    "2核4G": "S5.MEDIUM8",
    "4核8G": "S5.LARGE8",
    "8核16G": "S5.2XLARGE16",
}


async def create_cvm_instance(name: str, spec: str | None = None) -> dict:
    """创建腾讯云 CVM 实例。"""
    instance_type = SPEC_MAP.get(spec, "S5.MEDIUM8") if spec else "S5.MEDIUM8"
    password = "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$") for _ in range(16))

    cred = get_tc_credential()
    client = cvm_client.CvmClient(cred, settings.tc_region)

    req = models.RunInstancesRequest()
    params = {
        "InstanceName": name,
        "InstanceType": instance_type,
        "ImageId": "img-eb30mz89",  # Ubuntu 22.04 LTS
        "SystemDisk": {"DiskType": "CLOUD_PREMIUM", "DiskSize": 50},
        "InstanceCount": 1,
        "InstanceChargeType": "POSTPAID_BY_HOUR",
        "LoginSettings": {"Password": password},
    }
    req.from_json_string(json.dumps(params))

    try:
        resp = client.RunInstances(req)
        result = json.loads(resp.to_json_string())
        instance_ids = result.get("InstanceIdSet", [])
        instance_id = instance_ids[0] if instance_ids else "unknown"

        logger.info("Tencent CVM created: id=%s name=%s type=%s", instance_id, name, instance_type)

        return {
            "resource_id": instance_id,
            "connection_info": f"实例 ID: {instance_id}\n密码: {password}\n(IP 请在腾讯云控制台查看)",
            "cost_estimate": None,
        }

    except TencentCloudSDKException as e:
        raise RuntimeError(f"腾讯云 CVM 创建失败: {e.message}") from e
