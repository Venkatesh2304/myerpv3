import os
import sys
import gc
import re
import shutil
import calendar
import datetime
import time
import logging
import subprocess
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import fitz  # PyMuPDF
from django.core.management.base import BaseCommand
from django.conf import settings

from core.models import Company
from report.models import SalesRegisterReport
from custom.classes import Billing


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Download bills from IKEA in parallel batches (up to 100-150 bills per batch with 10 workers), "
        "monitor disk space (halts if <500MB), compress each month into one PDF, and then compress "
        "the entire year into a single 7z archive and delete intermediate monthly PDFs to save space."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            type=str,
            default="devaki_hul",
            help="Company identifier (default: devaki_hul)",
        )
        parser.add_argument(
            "--start",
            type=str,
            default="2024-12",
            help="Start month (YYYY-MM) (default: 2024-12)",
        )
        parser.add_argument(
            "--end",
            type=str,
            default="2026-08",
            help="End month (YYYY-MM) (default: 2026-08)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of bills per batch request to IKEA (default: 100)",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=5,
            help="Number of concurrent worker threads (default: 5)",
        )
        parser.add_argument(
            "--min-space-mb",
            type=int,
            default=500,
            help="Safety threshold for free disk space in MB; aborts if below this (default: 500)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Process only this specific year (e.g. 2024, 2025, 2026)",
        )
        parser.add_argument(
            "--month",
            type=str,
            default=None,
            help="Process only this specific month (e.g. 2025-10)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download and re-compress even if monthly PDF or year archive already exists",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Inspect bill counts and batch breakdown without downloading PDFs",
        )

    def handle(self, *args, **options):
        company_id = options["company"]
        start_arg = options["start"]
        end_arg = options["end"]
        batch_size = options["batch_size"]
        workers = options["workers"]
        min_space_mb = options["min_space_mb"]
        year_filter = options["year"]
        month_filter = options["month"]
        force = options["force"]
        dry_run = options["dry_run"]

        try:
            company = Company.objects.get(name=company_id)
        except Company.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Company '{company_id}' not found in database."))
            return

        self.stdout.write(self.style.SUCCESS(f"=== Starting Bill Archiver for Company: {company_id} ==="))
        self.stdout.write(f"Batch Size: {batch_size} bills/request | Parallel Workers: {workers} threads")
        self.stdout.write(f"Disk Space Guardrail: Halt when free space < {min_space_mb} MB")

        # Check initial disk space
        is_safe, free_mb = self.check_disk_space(min_space_mb)
        self.stdout.write(f"Current Available Disk Space: {free_mb:.1f} MB")
        if not is_safe:
            self.stderr.write(
                self.style.ERROR(
                    f"ABORTED: Free disk space ({free_mb:.1f} MB) is below safe limit ({min_space_mb} MB)!"
                )
            )
            return

        # Determine target months
        months_to_process = self.get_target_months(
            start_arg=start_arg,
            end_arg=end_arg,
            year_filter=year_filter,
            month_filter=month_filter,
        )

        if not months_to_process:
            self.stdout.write(self.style.WARNING("No months to process matching the criteria."))
            return

        self.stdout.write(
            f"Months to process: {', '.join([f'{y}-{m:02d}' for y, m in months_to_process])}"
        )

        # Check IKEA login
        if not dry_run:
            try:
                billing = Billing(company_id)
                if not billing.is_logged_in():
                    if not self.wait_for_ikea_login(company_id, max_retries=2, wait_minutes=30):
                        return
                    billing = Billing(company_id)
            except Exception:
                if not self.wait_for_ikea_login(company_id, max_retries=2, wait_minutes=30):
                    return
                billing = Billing(company_id)
        else:
            billing = None

        # Group months by year
        year_groups = {}
        for y, m in months_to_process:
            year_groups.setdefault(y, []).append(m)

        for year, months in sorted(year_groups.items()):
            year_dir = os.path.join(settings.MEDIA_ROOT, "bills", company_id, str(year))
            os.makedirs(year_dir, exist_ok=True)
            year_7z_path = os.path.join(year_dir, f"bills_{company_id}_{year}.7z")

            if os.path.exists(year_7z_path) and os.path.getsize(year_7z_path) > 0 and not force:
                s_mb = os.path.getsize(year_7z_path) / (1024 * 1024)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\nYear {year} already fully archived: bills_{company_id}_{year}.7z ({s_mb:.2f} MB). Skipping year."
                    )
                )
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n================ YEAR {year} ================"))
            yearly_results = []
            halted_early = False

            for month in sorted(months):
                self.stdout.write(f"\n--- Processing Month {year}-{month:02d} ---")
                sys.stdout.flush()

                # Check space before processing month
                is_safe, free_mb = self.check_disk_space(min_space_mb)
                if not is_safe:
                    self.stderr.write(
                        self.style.ERROR(
                            f"HALTING: Free disk space reached {free_mb:.1f} MB (threshold {min_space_mb} MB)!"
                        )
                    )
                    halted_early = True
                    break

                res = self.process_month(
                    company_id=company_id,
                    year=year,
                    month=month,
                    billing=billing,
                    batch_size=batch_size,
                    workers=workers,
                    min_space_mb=min_space_mb,
                    force=force,
                    dry_run=dry_run,
                )

                if res.get("status") == "halted_low_space":
                    halted_early = True
                    break

                if res.get("status") == "halted_auth":
                    self.stdout.write(
                        self.style.WARNING(
                            f"\nIKEA session expired at {month}/{year}. "
                            "Please push cookies from the desktop client to resume."
                        )
                    )
                    halted_early = True
                    break

                if res.get("status") in ("success", "skipped"):
                    yearly_results.append(res)

            # If all months for this year completed, create the consolidated Year 7z archive and delete intermediate PDFs!
            if not dry_run and not halted_early and len(yearly_results) == len(months):
                self.archive_year_and_cleanup(company_id=company_id, year=year, year_dir=year_dir)

            if halted_early:
                self.stdout.write(
                    self.style.WARNING(
                        f"\nProcessing paused. All completed months are safely preserved. You can resume anytime."
                    )
                )
                break

        self.stdout.write(self.style.SUCCESS("\nAll requested tasks completed."))

    def archive_year_and_cleanup(self, company_id: str, year: int, year_dir: str):
        """Compress all monthly PDFs of this year into a single 7z file and delete loose PDFs."""
        pdf_pattern = os.path.join(year_dir, f"bills_{company_id}_{year}_*.pdf")
        pdf_files = sorted(glob.glob(pdf_pattern))

        if not pdf_files:
            return

        year_7z_path = os.path.join(year_dir, f"bills_{company_id}_{year}.7z")
        self.stdout.write(
            f"\nCompressing {len(pdf_files)} monthly PDFs for Year {year} into {os.path.basename(year_7z_path)} (LZMA2)..."
        )
        sys.stdout.flush()

        cmd = [
            "7z",
            "a",
            "-t7z",
            "-m0=lzma2",
            "-mx=9",
            "-mmt=2",
            year_7z_path,
        ] + pdf_files

        try:
            subprocess.run(cmd, check=True)
            if os.path.exists(year_7z_path) and os.path.getsize(year_7z_path) > 0:
                s_mb = os.path.getsize(year_7z_path) / (1024 * 1024)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Year {year} successfully archived: {os.path.basename(year_7z_path)} ({s_mb:.2f} MB)"
                    )
                )

                # Delete individual monthly PDFs to save space
                self.stdout.write("Deleting intermediate monthly PDFs to reclaim disk space...")
                freed_bytes = 0
                for f in pdf_files:
                    try:
                        freed_bytes += os.path.getsize(f)
                        os.remove(f)
                    except Exception as e:
                        self.stderr.write(f"Could not remove {f}: {e}")

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Deleted {len(pdf_files)} monthly PDFs, freeing {freed_bytes / (1024 * 1024):.2f} MB!"
                    )
                )
                sys.stdout.flush()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error creating 7z archive for Year {year}: {e}"))

    def wait_for_ikea_login(self, company_id: str, max_retries: int = 2, wait_minutes: int = 30) -> bool:
        """
        Wait for IKEA login if cookies expired.
        Tries up to max_retries times, waiting wait_minutes (default 30 mins) between each attempt.
        Periodically polls every 30 seconds so if the user logs in sooner, it resumes immediately.
        If still not logged in after max_retries, returns False.
        """
        self.stdout.write(
            self.style.WARNING(
                f"\n[IKEA Login Required] IKEA is not logged in for '{company_id}'. "
                f"Will attempt 2 checks after {wait_minutes} minutes each. "
                "Please push fresh cookies from the desktop client to resume."
            )
        )
        sys.stdout.flush()

        for attempt in range(1, max_retries + 1):
            self.stdout.write(
                f"\n[Attempt {attempt}/{max_retries}] Waiting {wait_minutes} minutes for login..."
            )
            sys.stdout.flush()

            total_wait_seconds = wait_minutes * 60
            poll_interval = 30
            elapsed = 0

            while elapsed < total_wait_seconds:
                time.sleep(poll_interval)
                elapsed += poll_interval
                try:
                    b = Billing(company_id)
                    if b.is_logged_in():
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"\n[IKEA Login Detected] Successfully logged in on attempt {attempt}! Resuming process."
                            )
                        )
                        sys.stdout.flush()
                        return True
                except Exception:
                    pass

                if elapsed % 300 == 0:
                    remaining_mins = (total_wait_seconds - elapsed) // 60
                    self.stdout.write(
                        f"  Waiting for login... {remaining_mins} min left in attempt {attempt}."
                    )
                    sys.stdout.flush()

            try:
                b = Billing(company_id)
                if b.is_logged_in():
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"\n[IKEA Login Detected] Successfully logged in! Resuming process."
                        )
                    )
                    sys.stdout.flush()
                    return True
            except Exception:
                pass

            self.stdout.write(
                self.style.WARNING(
                    f"[Attempt {attempt}/{max_retries}] {wait_minutes} minutes elapsed, still not logged in."
                )
            )
            sys.stdout.flush()

        self.stderr.write(
            self.style.ERROR(
                f"\nFailed to log in to IKEA after {max_retries} attempts ({max_retries * wait_minutes} minutes). "
                "Backend cannot log in directly. Stopping process."
            )
        )
        sys.stdout.flush()
        return False

    def check_disk_space(self, min_space_mb: int) -> tuple[bool, float]:
        """Check available disk space in MB."""
        usage = shutil.disk_usage("/")
        free_mb = usage.free / (1024 * 1024)
        return free_mb >= min_space_mb, free_mb

    def get_target_months(
        self,
        start_arg: str,
        end_arg: str,
        year_filter: int | None = None,
        month_filter: str | None = None,
    ) -> list[tuple[int, int]]:
        """Parse start and end into a list of (year, month) tuples."""
        if month_filter:
            parts = month_filter.split("-")
            return [(int(parts[0]), int(parts[1]))]

        def parse_to_ym(s: str) -> tuple[int, int]:
            parts = s.strip().split("-")
            return int(parts[0]), int(parts[1])

        start_y, start_m = parse_to_ym(start_arg)
        end_y, end_m = parse_to_ym(end_arg)

        results = []
        curr_y, curr_m = start_y, start_m
        while (curr_y < end_y) or (curr_y == end_y and curr_m <= end_m):
            if year_filter is None or curr_y == year_filter:
                results.append((curr_y, curr_m))
            curr_m += 1
            if curr_m > 12:
                curr_m = 1
                curr_y += 1

        return results

    def get_bills_for_month(
        self, company_id: str, year: int, month: int, billing: Billing
    ) -> list[str]:
        """Retrieve all bill numbers for the month from DB or live IKEA."""
        _, last_day = calendar.monthrange(year, month)
        fromd = datetime.date(year, month, 1)
        tod = datetime.date(year, month, last_day)

        # 1. Check internal database first
        db_bills = list(
            SalesRegisterReport.objects.filter(
                company_id=company_id,
                type="sales",
                date__range=(fromd, tod),
            )
            .values_list("inum", flat=True)
            .distinct()
        )

        if db_bills:
            cleaned = [b.strip() for b in db_bills if b and str(b).strip().lower() != "nan"]
            if cleaned:
                self.stdout.write(f"Found {len(cleaned)} bills in database for {year}-{month:02d}.")
                return sorted(list(set(cleaned)))

        # 2. Fetch live from IKEA sales register
        self.stdout.write(
            f"Month {year}-{month:02d} not found in database. Fetching sales register from IKEA..."
        )
        try:
            df = billing.sales_reg(fromd, tod)
            if df.empty or "BillRefNo" not in df.columns:
                self.stdout.write(self.style.WARNING(f"No bills found from IKEA for {year}-{month:02d}."))
                return []

            bills = df["BillRefNo"].dropna().astype(str).str.strip().unique().tolist()
            cleaned = [b for b in bills if b and b.lower() != "nan"]
            self.stdout.write(f"Fetched {len(cleaned)} bills from IKEA for {year}-{month:02d}.")
            return sorted(list(set(cleaned)))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error fetching sales register from IKEA: {e}"))
            return []

    def group_and_chunk_bills(
        self, bills: list[str], max_batch_size: int = 100
    ) -> list[tuple[int, str, str, int]]:
        """
        Group bills by prefix, sort numerically within prefix,
        and chunk into slices where count <= max_batch_size AND numeric serial span <= 180.
        Returns list of (batch_idx, b_first, b_last, count).
        """
        def parse_bill(b):
            m = re.match(r"^([A-Za-z]+)(\d+)$", b.strip())
            if m:
                return m.group(1), int(m.group(2)), b.strip()
            return "", 0, b.strip()

        parsed = [parse_bill(b) for b in bills if b and str(b).lower() != "nan"]
        by_prefix = {}
        for prefix, num, orig in parsed:
            by_prefix.setdefault(prefix, []).append((num, orig))

        batches = []
        batch_idx = 0

        for prefix, items in sorted(by_prefix.items()):
            if not prefix:
                for _, orig in items:
                    batches.append((batch_idx, orig, orig, 1))
                    batch_idx += 1
                continue

            # Sort by serial number
            items.sort(key=lambda x: x[0])
            unique_items = []
            seen = set()
            for num, orig in items:
                if num not in seen:
                    seen.add(num)
                    unique_items.append((num, orig))

            # Chunk into slices where count <= max_batch_size AND numeric span <= 180
            curr_chunk = []
            for num, orig in unique_items:
                if not curr_chunk:
                    curr_chunk.append((num, orig))
                else:
                    if len(curr_chunk) >= max_batch_size or (num - curr_chunk[0][0]) >= 180:
                        batches.append((batch_idx, curr_chunk[0][1], curr_chunk[-1][1], len(curr_chunk)))
                        batch_idx += 1
                        curr_chunk = [(num, orig)]
                    else:
                        curr_chunk.append((num, orig))
            if curr_chunk:
                batches.append((batch_idx, curr_chunk[0][1], curr_chunk[-1][1], len(curr_chunk)))
                batch_idx += 1

        return batches

    def process_month(
        self,
        company_id: str,
        year: int,
        month: int,
        billing: Billing,
        batch_size: int,
        workers: int,
        min_space_mb: int,
        force: bool,
        dry_run: bool,
    ) -> dict:
        """
        Process a single month with parallel worker downloading.
        """
        month_name = calendar.month_name[month]
        year_dir = os.path.join(settings.MEDIA_ROOT, "bills", company_id, str(year))
        os.makedirs(year_dir, exist_ok=True)

        final_pdf_name = f"bills_{company_id}_{year}_{month:02d}.pdf"
        final_pdf_path = os.path.join(year_dir, final_pdf_name)

        # If already exists and not force, skip!
        if os.path.exists(final_pdf_path) and os.path.getsize(final_pdf_path) > 0 and not force:
            size_mb = os.path.getsize(final_pdf_path) / (1024 * 1024)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Month {month_name} {year} already completed: {final_pdf_name} ({size_mb:.2f} MB). Skipping."
                )
            )
            return {
                "status": "skipped",
                "year": year,
                "month": month,
                "month_name": month_name,
                "path": final_pdf_path,
                "filename": final_pdf_name,
                "size_mb": size_mb,
            }

        bills = self.get_bills_for_month(company_id, year, month, billing)
        if not bills:
            self.stdout.write(self.style.WARNING(f"No bills for {month_name} {year}."))
            return {"status": "empty", "year": year, "month": month, "month_name": month_name}

        batches = self.group_and_chunk_bills(bills, max_batch_size=batch_size)
        self.stdout.write(
            f"Total bills: {len(bills)} | Batches created: {len(batches)} "
            f"({batch_size} bills/batch, using {workers} parallel workers)"
        )

        if dry_run:
            self.stdout.write(
                f"[Dry Run] Would download {len(batches)} batches across {workers} workers for {month_name} {year}."
            )
            return {
                "status": "dry_run",
                "year": year,
                "month": month,
                "month_name": month_name,
                "bills_count": len(bills),
                "batches_count": len(batches),
            }

        temp_dir = os.path.join(settings.MEDIA_ROOT, "bills", ".temp", f"{company_id}_{year}_{month:02d}")
        os.makedirs(temp_dir, exist_ok=True)

        # Worker download function
        completed_count = 0
        total_batches = len(batches)
        lock = threading.Lock()
        low_space_halted = threading.Event()
        auth_halted = threading.Event()

        def fetch_batch_worker(batch_item):
            nonlocal completed_count
            if low_space_halted.is_set() or auth_halted.is_set():
                return None

            idx, b_first, b_last, count = batch_item
            batch_filename = f"batch_{idx:04d}.pdf"
            batch_filepath = os.path.join(temp_dir, batch_filename)

            if os.path.exists(batch_filepath) and os.path.getsize(batch_filepath) > 0:
                with lock:
                    completed_count += 1
                return batch_filepath

            # Check disk space
            is_safe, free_mb = self.check_disk_space(min_space_mb)
            if not is_safe:
                low_space_halted.set()
                return None

            # Local billing session for thread safety
            try:
                local_billing = Billing(company_id)
            except Exception as e_auth:
                self.stderr.write(f"IKEA Authentication error in worker: {e_auth}")
                auth_halted.set()
                return None

            pdf_bytes = None

            for attempt in range(4):
                if low_space_halted.is_set() or auth_halted.is_set():
                    return None
                try:
                    pdf_bytes = local_billing.get_bill_new_pdf(b_first, b_last)
                    if pdf_bytes and len(pdf_bytes.getvalue()) > 500:
                        break
                    else:
                        pdf_bytes = None
                except Exception:
                    time.sleep(2 * (attempt + 1))

            if not pdf_bytes or len(pdf_bytes.getvalue()) < 500:
                self.stderr.write(f"Batch {idx + 1}/{total_batches} ({b_first}..{b_last}) failed.")
                return None

            with open(batch_filepath, "wb") as f:
                f.write(pdf_bytes.getvalue())

            del pdf_bytes

            with lock:
                completed_count += 1
                curr_done = completed_count
                pct = (curr_done / total_batches) * 100
                self.stdout.write(
                    f"  [Progress] {curr_done}/{total_batches} batches finished ({pct:.1f}%) "
                    f"-> Batch {b_first}..{b_last} ({count} bills)"
                )
                sys.stdout.flush()

            return batch_filepath

        self.stdout.write(f"Launching {workers} parallel download workers...")
        sys.stdout.flush()

        batch_files = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_batch = {executor.submit(fetch_batch_worker, b): b for b in batches}
            for future in as_completed(future_to_batch):
                result = future.result()
                if result:
                    batch_files.append(result)

        if auth_halted.is_set():
            self.stdout.write(
                self.style.WARNING(
                    f"\nIKEA session expired while processing {month_name} {year}. "
                    "Waiting to retry login (2 attempts after 30 minutes)..."
                )
            )
            re_authed = self.wait_for_ikea_login(company_id, max_retries=2, wait_minutes=30)
            if not re_authed:
                return {
                    "status": "halted_auth",
                    "year": year,
                    "month": month,
                    "month_name": month_name,
                }
            auth_halted.clear()
            # Retry remaining missing batches
            self.stdout.write(f"Resuming missing batches for {month_name} {year}...")
            missing_batches = [
                b for b in batches
                if not os.path.exists(os.path.join(temp_dir, f"batch_{b[0]:04d}.pdf"))
            ]
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_batch = {executor.submit(fetch_batch_worker, b): b for b in missing_batches}
                for future in as_completed(future_to_batch):
                    result = future.result()
                    if result:
                        batch_files.append(result)

        if low_space_halted.is_set():
            _, free_mb = self.check_disk_space(min_space_mb)
            self.stderr.write(
                self.style.ERROR(
                    f"Disk space reached {free_mb:.1f} MB (limit: {min_space_mb} MB). Halting batch download."
                )
            )
            return {
                "status": "halted_low_space",
                "free_mb": free_mb,
                "year": year,
                "month": month,
                "month_name": month_name,
            }

        if not batch_files:
            self.stderr.write(self.style.ERROR(f"No batches successfully downloaded for {month_name} {year}."))
            return {"status": "failed", "year": year, "month": month, "month_name": month_name}

        # Merge all batch PDFs and apply compression
        self.stdout.write(f"Merging and saving for {month_name} {year}...")
        sys.stdout.flush()

        master_doc = fitz.open()
        for bf in sorted(batch_files):
            try:
                sub_doc = fitz.open(bf)
                master_doc.insert_pdf(sub_doc)
                sub_doc.close()
            except Exception as e:
                self.stderr.write(f"Error appending batch {bf}: {e}")

        total_pages = len(master_doc)
        self.stdout.write(f"Combined {total_pages} pages. Saving compressed PDF...")
        sys.stdout.flush()

        temp_output_path = final_pdf_path + ".tmp"
        master_doc.save(
            temp_output_path,
            deflate=True,
            garbage=3,
            clean=True,
        )
        master_doc.close()
        os.replace(temp_output_path, final_pdf_path)

        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            self.stderr.write(f"Warning: could not remove temp folder {temp_dir}: {e}")

        final_size_mb = os.path.getsize(final_pdf_path) / (1024 * 1024)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully generated: {final_pdf_name} ({total_pages} pages, {final_size_mb:.2f} MB)"
            )
        )
        sys.stdout.flush()

        return {
            "status": "success",
            "year": year,
            "month": month,
            "month_name": month_name,
            "bills_count": len(bills),
            "pages": total_pages,
            "path": final_pdf_path,
            "filename": final_pdf_name,
            "size_mb": final_size_mb,
        }
