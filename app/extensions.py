"""
Shared Flask extension instances, kept in their own module so both
__init__.py (which initializes them) and routes.py (which uses them as
decorators) can import without a circular-import problem.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# No global default limit -- individual routes opt in explicitly. This is a
# free, unauthenticated, personal-scale tool; the only endpoint that needs
# protection is /analyze, since it's the one that triggers outbound calls to
# Yahoo Finance and does real computation per request.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
