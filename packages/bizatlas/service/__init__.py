"""服务层（阶段 3）：健康探针等部署支撑。"""

from bizatlas.service.health import liveness, readiness

__all__ = ["liveness", "readiness"]
