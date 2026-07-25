"""Import every domain model module so they register with Base.metadata.

Alembic's autogenerate (and any create_all fallback) needs all mapped
classes imported at least once before it can see their tables.
"""

from app.domain.agents import models as _agents_models  # noqa: F401
from app.domain.storage import models as _storage_models  # noqa: F401
from app.domain.documents import models as _documents_models  # noqa: F401
from app.domain.tenancy import models as _tenancy_models  # noqa: F401
from app.domain.workflow import models as _workflow_models  # noqa: F401
from app.domain.workflow_instances import models as _workflow_instances_models  # noqa: F401
from app.domain.shared.base import Base

metadata = Base.metadata
