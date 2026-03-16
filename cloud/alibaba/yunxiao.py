"""云效 Flow API — 创建和管理 CI/CD 流水线。

SDK: alibabacloud-devops20210625
文档: https://help.aliyun.com/zh/yunxiao/developer-reference/api-overview

核心 API:
- CreatePipeline — 创建流水线
- StartPipelineRun — 触发流水线运行
- ListPipelines — 列出流水线
"""

import json
import logging

from alibabacloud_devops20210625.client import Client as DevopsClient
from alibabacloud_devops20210625.models import (
    CreatePipelineRequest,
    StartPipelineRunRequest,
)

from cloud.alibaba import get_ali_config
from config import settings

logger = logging.getLogger(__name__)

# 云效 Flow 流水线 YAML 模板 (按语言)
PIPELINE_YAML_TEMPLATES = {
    "java_maven": """sources:
  gitee_source:
    type: codeSource
    endpoint: {gitee_repo}
    branch: {branch}
    isTrigger: true
stages:
  build_stage:
    jobs:
      build:
        steps:
          - step: JavaBuild
            name: Maven 构建
            with:
              jdkVersion: "11"
              mavenVersion: "3.9"
              run: mvn clean package -DskipTests -B
          - step: DockerBuild
            name: 构建镜像
            with:
              dockerfilePath: Dockerfile
              imageRepo: {acr_registry}/{acr_namespace}/{service_name}
  deploy_stage:
    jobs:
      deploy:
        steps:
          - step: KubectlApply
            name: 部署到 {env_label}
            with:
              clusterId: {ack_cluster_id}
              namespace: {namespace}
""",
    "java_gradle": """sources:
  gitee_source:
    type: codeSource
    endpoint: {gitee_repo}
    branch: {branch}
    isTrigger: true
stages:
  build_stage:
    jobs:
      build:
        steps:
          - step: JavaBuild
            name: Gradle 构建
            with:
              jdkVersion: "11"
              run: ./gradlew build -x test --no-daemon
          - step: DockerBuild
            name: 构建镜像
            with:
              dockerfilePath: Dockerfile
              imageRepo: {acr_registry}/{acr_namespace}/{service_name}
  deploy_stage:
    jobs:
      deploy:
        steps:
          - step: KubectlApply
            name: 部署到 {env_label}
            with:
              clusterId: {ack_cluster_id}
              namespace: {namespace}
""",
    "nodejs": """sources:
  gitee_source:
    type: codeSource
    endpoint: {gitee_repo}
    branch: {branch}
    isTrigger: true
stages:
  build_stage:
    jobs:
      build:
        steps:
          - step: NpmBuild
            name: Node.js 构建
            with:
              nodeVersion: "20"
              run: npm ci && npm run build
          - step: DockerBuild
            name: 构建镜像
            with:
              dockerfilePath: Dockerfile
              imageRepo: {acr_registry}/{acr_namespace}/{service_name}
  deploy_stage:
    jobs:
      deploy:
        steps:
          - step: KubectlApply
            name: 部署到 {env_label}
            with:
              clusterId: {ack_cluster_id}
              namespace: {namespace}
""",
    "python": """sources:
  gitee_source:
    type: codeSource
    endpoint: {gitee_repo}
    branch: {branch}
    isTrigger: true
stages:
  build_stage:
    jobs:
      build:
        steps:
          - step: DockerBuild
            name: 构建镜像
            with:
              dockerfilePath: Dockerfile
              imageRepo: {acr_registry}/{acr_namespace}/{service_name}
  deploy_stage:
    jobs:
      deploy:
        steps:
          - step: KubectlApply
            name: 部署到 {env_label}
            with:
              clusterId: {ack_cluster_id}
              namespace: {namespace}
""",
}


def _get_client() -> DevopsClient:
    config = get_ali_config()
    config.endpoint = "devops.cn-hangzhou.aliyuncs.com"
    return DevopsClient(config)


async def create_pipeline(
    service_name: str,
    gitee_repo: str,
    branch: str,
    language: str,
    environment: str,
) -> str:
    """在云效上创建 CI/CD 流水线。

    Args:
        service_name: 服务名
        gitee_repo: Gitee 仓库地址
        branch: 分支
        language: 语言类型 (java_maven/java_gradle/nodejs/python)
        environment: 环境 (test/production)

    Returns:
        pipeline_id: 云效流水线 ID
    """
    env_label = "测试环境" if environment == "test" else "生产环境"
    namespace = f"{service_name}-{environment}"

    # 生成流水线 YAML
    template = PIPELINE_YAML_TEMPLATES.get(language, PIPELINE_YAML_TEMPLATES["java_maven"])
    pipeline_yaml = template.format(
        gitee_repo=gitee_repo,
        branch=branch,
        service_name=service_name,
        acr_registry=settings.ali_acr_registry,
        acr_namespace=settings.ali_acr_namespace,
        ack_cluster_id=settings.ali_ack_cluster_id,
        namespace=namespace,
        env_label=env_label,
    )

    client = _get_client()

    request = CreatePipelineRequest(
        organization_id=settings.ali_devops_org_id,
        pipeline_name=f"{service_name}-{environment}",
        content=pipeline_yaml,
    )

    response = client.create_pipeline(request)

    if not response.body or not response.body.pipeline:
        raise RuntimeError(f"Failed to create pipeline: {response}")

    pipeline_id = str(response.body.pipeline.id)
    logger.info("Created Yunxiao pipeline: id=%s name=%s-%s", pipeline_id, service_name, environment)
    return pipeline_id


async def run_pipeline(pipeline_id: str) -> str:
    """触发云效流水线运行。

    Returns:
        run_id: 运行 ID
    """
    client = _get_client()

    request = StartPipelineRunRequest(
        organization_id=settings.ali_devops_org_id,
        pipeline_id=int(pipeline_id),
    )

    response = client.start_pipeline_run(request)
    run_id = str(response.body.pipeline_run_id) if response.body else "unknown"
    logger.info("Started pipeline run: pipeline=%s run=%s", pipeline_id, run_id)
    return run_id
