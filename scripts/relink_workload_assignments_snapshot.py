"""Relink active workload assignments to the current population snapshot."""

from __future__ import annotations

import argparse
from app import create_app
from app.core.extensions import db
from app.models import PopulationSnapshot, TariffVersion
from app.services.workload_snapshot_service import (
    relink_assignments_to_population_snapshot,
)


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-id", type=int, required=True)
    parser.add_argument("--target-snapshot-id", type=int)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def _target_snapshot(version_id, snapshot_id):
    query = PopulationSnapshot.query.filter_by(tariff_version_id=version_id)
    if snapshot_id is not None:
        snapshot = query.filter_by(id=snapshot_id).one_or_none()
    else:
        snapshot = query.filter_by(status="CURRENT").one_or_none()
    if snapshot is None:
        raise RuntimeError("Current population snapshot was not found.")
    return snapshot


def run(version_id, target_snapshot_id=None, apply_changes=False):
    target_snapshot = _target_snapshot(version_id, target_snapshot_id)
    version = db.session.get(TariffVersion, version_id)
    if version is None:
        raise RuntimeError("Tariff version was not found.")
    actor_user_id = target_snapshot.created_by_user_id
    if apply_changes and actor_user_id is None:
        raise RuntimeError("Target snapshot has no author for the audit trail.")

    changed = relink_assignments_to_population_snapshot(
        version,
        target_snapshot,
        user_id=actor_user_id,
    )
    if not apply_changes:
        db.session.rollback()
        print(
            f"target_snapshot={target_snapshot.id} "
            f"would_relink={changed} dry_run=true"
        )
        return
    db.session.commit()
    print(f"target_snapshot={target_snapshot.id} applied={changed}")


if __name__ == "__main__":
    args = _arguments()
    app = create_app()
    with app.app_context():
        run(
            version_id=args.version_id,
            target_snapshot_id=args.target_snapshot_id,
            apply_changes=args.apply,
        )
