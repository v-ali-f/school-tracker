from app import create_app
from app.__init__ import _seed_olympiad_subject_mappings

app = create_app()
_seed_olympiad_subject_mappings(app)
print('Готово: базовые предметы ВСОШ загружены.')
