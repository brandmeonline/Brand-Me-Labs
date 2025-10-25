#!/usr/bin/env python3
"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Database Management CLI
=======================

Provides commands for:
- Running migrations
- Seeding data
- Resetting database
- Exporting user data (GDPR compliance)
"""

import os
import sys
import click
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Load environment variables
load_dotenv()

console = Console()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/brandme_dev")
SCHEMAS_DIR = Path(__file__).parent / "schemas"
SEEDS_DIR = Path(__file__).parent / "seeds"


def get_connection():
    """Get database connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        console.print(f"[red]Failed to connect to database: {e}[/red]")
        sys.exit(1)


@click.group()
def cli():
    """Brand.Me Database Management CLI"""
    pass


@cli.command()
def migrate():
    """Run all database migrations."""
    console.print("[bold blue]Running database migrations...[/bold blue]")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get all schema files in order
        schema_files = sorted(SCHEMAS_DIR.glob("*.sql"))

        if not schema_files:
            console.print("[yellow]No schema files found[/yellow]")
            return

        for schema_file in schema_files:
            console.print(f"  Applying: {schema_file.name}")
            with open(schema_file, 'r') as f:
                sql = f.read()
                cursor.execute(sql)

        conn.commit()
        console.print("[green]✓ Migrations completed successfully[/green]")

    except Exception as e:
        conn.rollback()
        console.print(f"[red]✗ Migration failed: {e}[/red]")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


@cli.command()
@click.option('--fixture', default=None, help='Specific fixture to seed (users, garments, etc.)')
@click.option('--clear', is_flag=True, help='Clear existing data before seeding')
def seed(fixture, clear):
    """Seed database with development data."""
    console.print("[bold blue]Seeding database...[/bold blue]")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        if clear:
            console.print("[yellow]Clearing existing data...[/yellow]")
            # Clear in reverse dependency order
            tables = [
                'audit_log',
                'chain_anchor',
                'scan_event',
                'consent_policies',
                'garment_passport_facets',
                'garments',
                'users'
            ]
            for table in tables:
                cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
            conn.commit()
            console.print("[green]✓ Data cleared[/green]")

        # Get seed files
        if fixture:
            seed_files = [SEEDS_DIR / f"{fixture}.sql"]
        else:
            seed_files = sorted(SEEDS_DIR.glob("*.sql"))

        if not seed_files:
            console.print("[yellow]No seed files found[/yellow]")
            return

        for seed_file in seed_files:
            if not seed_file.exists():
                console.print(f"[yellow]Seed file not found: {seed_file.name}[/yellow]")
                continue

            console.print(f"  Seeding: {seed_file.name}")
            with open(seed_file, 'r') as f:
                sql = f.read()
                cursor.execute(sql)

        conn.commit()
        console.print("[green]✓ Seeding completed successfully[/green]")

    except Exception as e:
        conn.rollback()
        console.print(f"[red]✗ Seeding failed: {e}[/red]")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


@cli.command()
@click.confirmation_option(prompt='Are you sure you want to reset the database? This will delete ALL data.')
def reset():
    """Reset database (drop all tables and re-create)."""
    console.print("[bold red]Resetting database...[/bold red]")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Drop all tables in reverse dependency order
        console.print("[yellow]Dropping tables...[/yellow]")
        tables = [
            'audit_log',
            'chain_anchor',
            'scan_event',
            'consent_policies',
            'garment_passport_facets',
            'garments',
            'users'
        ]
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

        conn.commit()
        console.print("[green]✓ Tables dropped[/green]")

        # Run migrations
        console.print("[blue]Running migrations...[/blue]")
        cursor.close()
        conn.close()

        # Call migrate command
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(migrate)

        if result.exit_code == 0:
            console.print("[green]✓ Database reset completed[/green]")
        else:
            console.print("[red]✗ Reset failed during migrations[/red]")
            sys.exit(1)

    except Exception as e:
        conn.rollback()
        console.print(f"[red]✗ Reset failed: {e}[/red]")
        sys.exit(1)


@cli.command()
def status():
    """Show database status and table counts."""
    console.print("[bold blue]Database Status[/bold blue]\n")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Create table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Table", style="cyan", no_wrap=True)
        table.add_column("Row Count", justify="right", style="green")

        tables = [
            'users',
            'garments',
            'garment_passport_facets',
            'consent_policies',
            'scan_event',
            'chain_anchor',
            'audit_log'
        ]

        for tbl in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
            count = cursor.fetchone()[0]
            table.add_row(tbl, str(count))

        console.print(table)

        # Check audit chain integrity
        console.print("\n[bold blue]Audit Chain Integrity[/bold blue]")
        cursor.execute("SELECT * FROM v_audit_chain_integrity")
        integrity = cursor.fetchone()

        if integrity:
            total, valid, broken, is_intact = integrity
            console.print(f"  Total entries: {total}")
            console.print(f"  Valid links: {valid}")
            console.print(f"  Broken links: {broken}")

            if is_intact:
                console.print("  Status: [green]✓ Chain is intact[/green]")
            else:
                console.print("  Status: [red]✗ Chain has broken links[/red]")

    except Exception as e:
        console.print(f"[red]✗ Failed to get status: {e}[/red]")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


@cli.command()
@click.argument('user_id')
@click.option('--output', default='user_data_export.json', help='Output file path')
def export_user_data(user_id, output):
    """Export all data for a specific user (GDPR compliance)."""
    console.print(f"[bold blue]Exporting data for user: {user_id}[/bold blue]")

    import json

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Export user data
        export_data = {}

        # User info
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            console.print(f"[red]User not found: {user_id}[/red]")
            sys.exit(1)

        export_data['user'] = dict(zip([desc[0] for desc in cursor.description], user))

        # Garments created
        cursor.execute("SELECT * FROM garments WHERE creator_id = %s", (user_id,))
        export_data['garments_created'] = [
            dict(zip([desc[0] for desc in cursor.description], row))
            for row in cursor.fetchall()
        ]

        # Garments owned
        cursor.execute("SELECT * FROM garments WHERE current_owner_id = %s", (user_id,))
        export_data['garments_owned'] = [
            dict(zip([desc[0] for desc in cursor.description], row))
            for row in cursor.fetchall()
        ]

        # Scans performed
        cursor.execute("SELECT * FROM scan_event WHERE scanner_user_id = %s", (user_id,))
        export_data['scans'] = [
            dict(zip([desc[0] for desc in cursor.description], row))
            for row in cursor.fetchall()
        ]

        # Write to file
        with open(output, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        console.print(f"[green]✓ Data exported to: {output}[/green]")

    except Exception as e:
        console.print(f"[red]✗ Export failed: {e}[/red]")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


@cli.command()
def check_migrations():
    """Check if all migrations have been applied."""
    console.print("[bold blue]Checking migrations...[/bold blue]")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Check if all tables exist
        expected_tables = [
            'users',
            'garments',
            'garment_passport_facets',
            'consent_policies',
            'scan_event',
            'chain_anchor',
            'audit_log'
        ]

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
        """)

        existing_tables = [row[0] for row in cursor.fetchall()]

        missing_tables = set(expected_tables) - set(existing_tables)

        if missing_tables:
            console.print(f"[red]✗ Missing tables: {', '.join(missing_tables)}[/red]")
            console.print("[yellow]Run 'python manage.py migrate' to apply migrations[/yellow]")
        else:
            console.print("[green]✓ All migrations applied[/green]")

    except Exception as e:
        console.print(f"[red]✗ Check failed: {e}[/red]")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    cli()
