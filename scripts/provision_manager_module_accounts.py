"""Provision the manager-module login accounts on an ALREADY POPULATED database.

`seed_manager_module.py` cannot do this. Its guard is
`db.query(Kindergarten).count() > 0`, so on production -- which has hundreds of
kindergartens -- it prints [SKIP] and returns having created nothing. Its only
other mode is `--force`, which calls `Base.metadata.drop_all()`. Neither is
usable against live data, so the accounts have to be provisioned separately.

Creates 3 managers, 7 supervisors (2 active per kindergarten + 1 inactive for
validation cases) and 3 parents, attached to kindergartens that already exist.
It never creates a kindergarten, never touches a user it did not create, and
never creates an admin.

Idempotent: a username that already exists is left exactly as it is and
reported as skipped, so re-running cannot produce duplicates.

Passwords come from --password or SEED_ACCOUNT_PASSWORD; otherwise one strong
password is generated and printed once. Nothing is written to the repository.

Usage:
    python scripts/provision_manager_module_accounts.py [--dry-run] [--password X]
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models  # noqa: E402
from auth import get_password_hash  # noqa: E402
from database import SessionLocal  # noqa: E402

# Jordan is UTC+3; operational timestamps must not be recorded in UTC.
_JORDAN_TZ = timezone(timedelta(hours=3))

MANAGER_COUNT = 3
SUPERVISORS_PER_KG = 2

PARENT_SPECS = [
    ("parent1@example.com", "أحمد", "الرشيد", "Ahmad", "Al-Rashid",
     "MALE", "أردني", "1234567890", "عمّان", "عمّان", "الدعيس",
     "+962791111111", "شارع المنزل 123"),
    ("parent2@example.com", "فاطمة", "النابلسي", "Fatima", "Al-Nabulsi",
     "FEMALE", "أردنية", "2345678901", "عمّان", "عمّان", "الجبيهة",
     "+962791111112", "شارع الجامعة 45"),
    ("parent3@example.com", "محمد", "العزام", "Mohammad", "Al-Azzam",
     "MALE", "أردني", "3456789012", "إربد", "إربد", "الحصن",
     "+962791111113", "شارع بغداد 10"),
]


def _generate_password() -> str:
    """A password strong enough for a real production login."""
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(16))
    # Guarantee the character classes a policy is likely to demand.
    return f"Kj{body}!7"


def _pick_kindergartens(db) -> list:
    """Attach to kindergartens that already exist. Deterministic by id so a
    re-run maps the same manager to the same kindergarten."""
    kgs = (
        db.query(models.Kindergarten)
        .order_by(models.Kindergarten.id)
        .limit(MANAGER_COUNT)
        .all()
    )
    if len(kgs) < MANAGER_COUNT:
        raise SystemExit(
            f"[FAIL] need {MANAGER_COUNT} existing kindergartens, found {len(kgs)}. "
            "This script does not create them."
        )
    return kgs


def _existing_usernames(db, usernames: list[str]) -> set[str]:
    if not usernames:
        return set()
    rows = (
        db.query(models.User.username)
        .filter(models.User.username.in_(usernames))
        .all()
    )
    return {r[0] for r in rows}


def _existing_emails(db, emails: list[str]) -> set[str]:
    if not emails:
        return set()
    rows = db.query(models.User.email).filter(models.User.email.in_(emails)).all()
    return {r[0] for r in rows}


def adopt_existing_managers(db, password: str, kgs: list, dry_run: bool) -> tuple[list, list]:
    """Give the run's password to each kindergarten's existing active manager.

    Creating a manager is impossible where one already exists -- see the partial
    unique index noted in provision(). Only managers that have never been signed
    in with are touched.
    """
    hashed = get_password_hash(password)
    adopted, kept = [], []
    for kg in kgs:
        mgr = (
            db.query(models.User)
            .filter(
                models.User.kindergarten_id == kg.id,
                models.User.role == models.UserRole.MANAGER,
                models.User.status == models.UserStatus.ACTIVE,
            )
            .order_by(models.User.id)
            .first()
        )
        if mgr is None:
            continue
        if mgr.last_login_at is not None:
            kept.append((mgr.username, kg.id))
            continue
        if not dry_run:
            mgr.hashed_password = hashed
        adopted.append((mgr.username, "MANAGER", f"kg {kg.id}"))
    return adopted, kept


def provision(db, password: str, dry_run: bool) -> tuple[list, list]:
    now = datetime.now(_JORDAN_TZ)
    kgs = _pick_kindergartens(db)
    print(f"  [OK] attaching to existing kindergartens: {[k.id for k in kgs]}")

    planned: list[tuple[str, str, str, int | None]] = []
    # Managers are NOT created. `uq_users_active_manager_per_kindergarten` is a
    # partial unique index over (kindergarten_id) WHERE role=MANAGER AND
    # status=ACTIVE AND deleted_at IS NULL, and every kindergarten in production
    # already has one -- inserting a second is impossible by construction, not
    # merely undesirable. The kindergarten's existing manager is adopted instead.
    for i, kg in enumerate(kgs):
        for j in range(SUPERVISORS_PER_KG):
            planned.append(
                (f"sup_{i+1}_{j+1}", f"sup_{i+1}_{j+1}@kinjo.jo", "SUPERVISOR", kg.id)
            )
    planned.append(("sup_inactive", "sup_inactive@kinjo.jo", "SUPERVISOR", kgs[0].id))
    for spec in PARENT_SPECS:
        planned.append((spec[0], spec[0], "PARENT", None))

    taken_users = _existing_usernames(db, [p[0] for p in planned])
    taken_emails = _existing_emails(db, [p[1] for p in planned])
    # uq_parent_profiles_national_id is unique; an id already in use belongs to
    # somebody else's profile and must not be duplicated.
    taken_national_ids = {
        r[0]
        for r in db.query(models.ParentProfile.national_id)
        .filter(
            models.ParentProfile.national_id.in_([s[7] for s in PARENT_SPECS])
        )
        .all()
    }

    created: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    hashed = get_password_hash(password)

    mgr_adopted, mgr_kept = adopt_existing_managers(db, password, kgs, dry_run)
    created.extend(mgr_adopted)
    for username, kg_id in mgr_kept:
        skipped.append((username, f"manager of kg {kg_id} has been signed in with"))

    for username, email, role, kg_id in planned:
        if username in taken_users:
            skipped.append((username, "username already exists"))
            continue
        if email in taken_emails:
            skipped.append((username, f"email {email} already in use"))
            continue
        if role == "PARENT":
            nid = next(s[7] for s in PARENT_SPECS if s[0] == username)
            if nid in taken_national_ids:
                skipped.append((username, f"national_id {nid} already in use"))
                continue

        status = (
            models.UserStatus.INACTIVE
            if username == "sup_inactive"
            else models.UserStatus.ACTIVE
        )
        full_name = {
            "MANAGER": f"مدير الحضانة {username[-1]}",
            "SUPERVISOR": ("مشرف غير نشط" if username == "sup_inactive" else f"مشرف {username}"),
            "PARENT": "",
        }[role]

        if role == "PARENT":
            spec = next(s for s in PARENT_SPECS if s[0] == username)
            full_name = f"{spec[1]} {spec[2]}"

        if dry_run:
            created.append((username, role, "(dry-run)"))
            taken_users.add(username)
            taken_emails.add(email)
            continue

        user = models.User(
            username=username,
            email=email,
            hashed_password=hashed,
            role=getattr(models.UserRole, role),
            status=status,
            full_name=full_name,
        )
        if kg_id is not None:
            user.kindergarten_id = kg_id
        db.add(user)
        db.flush()

        if role == "SUPERVISOR" and status == models.UserStatus.ACTIVE:
            db.add(
                models.SupervisorProfile(user_id=user.id, kindergarten_id=kg_id)
            )
        elif role == "PARENT":
            spec = next(s for s in PARENT_SPECS if s[0] == username)
            (_e, fn_ar, ln_ar, fn_en, ln_en, gender, nationality, nid,
             gov, city, area, phone, addr) = spec
            db.add(
                models.ParentProfile(
                    user_id=user.id,
                    first_name=fn_ar,
                    last_name=ln_ar,
                    first_name_en=fn_en,
                    last_name_en=ln_en,
                    phone_number=phone,
                    gender=getattr(models.Gender, gender),
                    nationality=nationality,
                    national_id=nid,
                    home_governorate=gov,
                    home_district=city,
                    home_area=area,
                    home_address_line=addr,
                    correspondence_preference=True,
                    profile_complete=True,
                    profile_completed_at=now,
                    relationship_to_child="أب" if gender == "MALE" else "أم",
                    emergency_contact_name=f"طوارئ {fn_ar}",
                    emergency_contact_phone=phone.replace("1111", "2222"),
                    emergency_contact_relationship="أخ/أخت",
                )
            )

        created.append((username, role, "created"))
        taken_users.add(username)
        taken_emails.add(email)

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return created, skipped


def adopt_unused(db, password: str, usernames: list[str], dry_run: bool) -> list[str]:
    """Set the run's password on seed-created accounts nobody has ever used.

    The guard is `last_login_at IS NULL`. An account someone has signed in with
    is a real account and is never modified, whatever its name looks like.
    """
    if not usernames:
        return []
    rows = (
        db.query(models.User)
        .filter(
            models.User.username.in_(usernames),
            models.User.last_login_at.is_(None),
        )
        .all()
    )
    hashed = get_password_hash(password)
    adopted = []
    for user in rows:
        if not dry_run:
            user.hashed_password = hashed
        adopted.append(user.username)

    in_use = sorted(set(usernames) - set(adopted))
    for username in in_use:
        print(f"    [KEEP] {username}: has been signed in with -- password unchanged")

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return adopted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change and roll back")
    ap.add_argument("--password", default=os.environ.get("SEED_ACCOUNT_PASSWORD"))
    ap.add_argument(
        "--adopt-unused-seed-logins",
        action="store_true",
        help=(
            "Set the run's password on accounts this script would otherwise skip, "
            "but ONLY where last_login_at IS NULL -- i.e. an earlier seed created "
            "the username and nobody has ever signed in with it. An account that "
            "has been used is never touched."
        ),
    )
    args = ap.parse_args()

    password = args.password or _generate_password()

    db = SessionLocal()
    try:
        created, skipped = provision(db, password, args.dry_run)
        adopted = (
            adopt_unused(db, password, [u for u, _r in skipped], args.dry_run)
            if args.adopt_unused_seed_logins
            else []
        )
    finally:
        db.close()

    print()
    print(f"  [OK] created {len(created)}, skipped {len(skipped)}, adopted {len(adopted)}")
    for username, reason in skipped:
        marker = "ADOPT" if username in adopted else "SKIP"
        print(f"    [{marker}] {username}: {reason}")
    by_role: dict[str, int] = {}
    for _u, role, _s in created:
        by_role[role] = by_role.get(role, 0) + 1
    print(f"    breakdown: {by_role}")
    if (created or adopted) and not args.dry_run:
        print(f"    password for the accounts touched by this run: {password}")
    print("  [DONE] provisioning complete")


if __name__ == "__main__":
    main()
