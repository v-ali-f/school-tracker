from datetime import date

from app import create_app, db
from app.models import ChildMovement, ChildTransferHistory

app = create_app()

MAP = {
    'PROMOTED': 'transfer',
    'MANUAL': 'transfer',
    'REPEAT': 'repeat',
    'CONDITIONAL': 'conditional',
    'EXPELLED': 'leave',
    'ARCHIVED': 'leave',
    'TRANSFERRED_OUT': 'leave',
}

with app.app_context():
    created = 0
    for row in ChildTransferHistory.query.order_by(ChildTransferHistory.id.asc()).all():
        exists = ChildMovement.query.filter_by(
            child_id=row.child_id,
            movement_date=row.transfer_date,
            from_class_id=row.from_class_id,
            to_class_id=row.to_class_id,
            order_number=row.order_number,
        ).first()
        if exists:
            continue
        db.session.add(ChildMovement(
            child_id=row.child_id,
            academic_year_id=row.to_academic_year_id or row.from_academic_year_id,
            movement_type=MAP.get(row.transfer_type or '', 'transfer'),
            movement_date=row.transfer_date or date.today(),
            from_class_id=row.from_class_id,
            to_class_id=row.to_class_id,
            reason=row.comment,
            order_number=row.order_number,
            created_by=row.created_by,
        ))
        created += 1
    db.session.commit()
    print(f'Created movements: {created}')
