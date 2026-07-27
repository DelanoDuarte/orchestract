from app.infrastructure.db import model_registry  # noqa: F401

# Importing model_registry (not any single domain module) ensures every
# mapped class is registered before SQLAlchemy configures mappers -- several
# relationships (e.g. Document.contract) reference their target by string
# name, which only resolves if that target's module has been imported
# somewhere in the process first.
