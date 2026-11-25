"""Isolated post-extract iOS compatibility rules, keeping native_inputs.py strict."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from ios_server import native_registry, native_tables as rules
from ios_server.table_codec import master_rows, patch_master
from ios_server.update_types import NormalizationReport

INDEX_PATTERN = re.compile(r'Ver([0-9]+)_' + re.escape(rules.INDEX.token) + r'\.dat')
MST_NAME_PATTERN = re.compile(r'Ver([0-9]+)_([A-Za-z0-9]{8})\.dat')


def _atomic_write(path: Path, raw: bytes, *, readonly: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.' + path.name + '.', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if readonly:
            temporary.chmod(0o444)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _contained(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f'Compatibility path escapes root: {candidate}')
    if candidate.is_symlink():
        raise ValueError(f'Compatibility path cannot be a symlink: {candidate}')
    return candidate


def _layout_paths(root_dir: Path, managed: bool) -> dict:
    static = root_dir / 'static' if managed else root_dir
    native = root_dir / 'native' if managed else static / 'client/files'
    overlay = None if managed else root_dir / 'overlay'
    native_roots = [r for r in (overlay, native) if r is not None and r.exists()]
    return {
        'root': root_dir,
        'managed': managed,
        'static': static,
        'native': native,
        'native_roots': native_roots,
        'mst_dirs': [r / 'mst' for r in native_roots if (r / 'mst').is_dir()],
        'loc_dirs': [r / 'localized_texts/en' for r in native_roots if (r / 'localized_texts/en').is_dir()],
        'xml_path': static / 'client/shared_prefs/gamedata.xml',
        'registry_path': root_dir / 'registry.json',
    }


def _find_unregistered_mst(root_dir: Path, mst_dirs: list[Path]) -> list[Path]:
    allowed = {table.token for table in rules.TABLES if not table.localized}
    unregistered = []
    for folder in mst_dirs:
        _contained(root_dir, folder)
        for path in sorted(folder.glob('Ver*_*.dat')):
            _contained(root_dir, path)
            match = MST_NAME_PATTERN.fullmatch(path.name)
            if match is None or match[2] not in allowed:
                unregistered.append(path)
    return unregistered


def _find_latest_index(root_dir: Path, mst_dirs: list[Path]) -> Path | None:
    for folder in mst_dirs:
        _contained(root_dir, folder)
        matches = []
        for path in folder.glob(f'Ver*_{rules.INDEX.token}.dat'):
            match = INDEX_PATTERN.fullmatch(path.name)
            if match is not None and int(match[1]) > 0:
                matches.append((int(match[1]), path))
        if matches:
            return _contained(root_dir, max(matches, key=lambda item: item[0])[1])
    return None


def _find_localized_mismatches(root_dir: Path, mst_dirs: list[Path], loc_dirs: list[Path]) -> tuple[Path | None, dict[str, tuple[int, int, str]]]:
    index_path = _find_latest_index(root_dir, mst_dirs)
    if index_path is None:
        return None, {}
    index_raw = index_path.read_bytes()
    localized = rules.english_versions(index_raw, tables=rules.INPUT_TABLES)
    actual_by_name = {}
    for table in rules.INPUT_TABLES:
        if not table.localized:
            continue
        version = localized[table.name]
        filename = Path(table.path(version)).name
        for folder in loc_dirs:
            _contained(root_dir, folder)
            candidate = folder / filename
            if candidate.is_file():
                _contained(root_dir, candidate)
                raw = candidate.read_bytes()
                actual_by_name[table.name] = (version, len(raw), hashlib.md5(raw).hexdigest())
                break
    mismatches = {}
    for _, row, _ in master_rows(index_raw, rules.INDEX.key, mode=rules.INDEX.cipher):
        name = row.get('a4hXTIm0')
        if name in actual_by_name:
            version, size, md5 = actual_by_name[name]
            if str(row.get('MLOSu5E0')) != str(size) or str(row.get('zptmZGqa', '')).lower() != md5:
                mismatches[name] = (version, size, md5)
    return index_path, mismatches


def _parse_registry_json(registry_path: Path) -> dict[str, str] | None:
    if not registry_path.is_file():
        return None
    data = json.loads(registry_path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError('registry.json must be a JSON object')
    return {str(k): str(v) for k, v in data.items()}


def _parse_xml_map(xml_path: Path) -> dict[str, str] | None:
    if not xml_path.is_file():
        return None
    tree = ET.fromstring(xml_path.read_bytes())
    if tree.tag != 'map':
        raise ValueError('gamedata.xml root element must be <map>')
    values = {}
    for row in tree.findall('string'):
        name = row.get('name', '')
        if name.startswith('keyF_'):
            if name in values:
                raise ValueError('duplicate key in gamedata.xml: ' + name)
            values[name] = row.text or ''
    return values


def _registry_sync_needed(paths: dict) -> bool:
    xml_path = paths['xml_path']
    registry_path = paths['registry_path']
    if not xml_path.exists() and not registry_path.exists():
        return False
    if not xml_path.is_file():
        return True
    try:
        native_registry.registered(xml_path.read_bytes(), rules.BY_NAME)
        xml_map = _parse_xml_map(xml_path)
    except (ET.ParseError, ValueError):
        return True
    if registry_path.is_file():
        try:
            reg = _parse_registry_json(registry_path)
        except (ValueError, OSError):
            return True
        if reg != xml_map:
            return True
    return False


def _scan_table_versions(mst_dirs: list[Path], loc_dirs: list[Path], index_path: Path | None) -> dict[str, str]:
    versions = {}
    if index_path is not None and index_path.is_file():
        try:
            for name, ver in rules.english_versions(index_path.read_bytes(), tables=rules.INPUT_TABLES).items():
                versions['key' + name] = str(ver)
        except ValueError:
            pass
    for table in rules.TABLES:
        key = 'key' + table.name
        if key in versions:
            continue
        dirs = loc_dirs if table.localized else mst_dirs
        best = 0
        for folder in dirs:
            for path in folder.glob(f'Ver*_{table.token}.dat'):
                match = MST_NAME_PATTERN.fullmatch(path.name)
                if match is not None:
                    best = max(best, int(match[1]))
        if best > 0:
            versions[key] = str(best)
    return versions


def inspect_directory(root_dir: Path, managed: bool) -> NormalizationReport:
    """Read-only compatibility audit on a flat, managed, or staged directory."""
    try:
        paths = _layout_paths(root_dir, managed)
        unregistered = [
            path.relative_to(root_dir).as_posix()
            for path in _find_unregistered_mst(root_dir, paths['mst_dirs'])
        ]
        _, mismatches = _find_localized_mismatches(root_dir, paths['mst_dirs'], paths['loc_dirs'])
        registry_sync = _registry_sync_needed(paths)
        return NormalizationReport(
            unregistered_mst_files=tuple(sorted(unregistered)),
            localized_index_mismatches=tuple(sorted(mismatches)),
            registry_sync_needed=registry_sync,
        )
    except (OSError, ValueError) as exc:
        return NormalizationReport(
            unregistered_mst_files=(),
            localized_index_mismatches=(),
            registry_sync_needed=False,
            error=str(exc),
        )


def _normalize_directory(root_dir: Path, managed: bool) -> dict:
    """Apply compatibility normalizations inside root_dir; returns changed/pruned paths."""
    paths = _layout_paths(root_dir, managed)
    pruned = []
    for path in _find_unregistered_mst(root_dir, paths['mst_dirs']):
        rel = path.relative_to(root_dir).as_posix()
        path.unlink()
        pruned.append(rel)

    reconciled = []
    modified_files = []
    index_path, mismatches = _find_localized_mismatches(root_dir, paths['mst_dirs'], paths['loc_dirs'])
    if index_path is not None and mismatches:
        def transform(row):
            name = row.get('a4hXTIm0')
            if name in mismatches:
                version, size, md5 = mismatches[name]
                row.update({'00zAYGYS': str(version), 'zptmZGqa': md5, 'MLOSu5E0': str(size)})
            return row

        raw, _ = patch_master(index_path.read_bytes(), rules.INDEX.key, transform, mode=rules.INDEX.cipher)
        _atomic_write(index_path, raw, readonly=managed)
        reconciled = sorted(mismatches)
        modified_files.append(index_path.relative_to(root_dir).as_posix())

    registry_synced = False
    if _registry_sync_needed(paths):
        xml_path = paths['xml_path']
        registry_path = paths['registry_path']
        merged = {}
        try:
            xml_map = _parse_xml_map(xml_path) or {}
        except (ET.ParseError, ValueError):
            xml_map = {}
        try:
            reg_map = _parse_registry_json(registry_path) or {}
        except (ValueError, OSError):
            reg_map = {}
        allowed_keys = {'key' + name for name in rules.BY_NAME}
        for source in (xml_map, reg_map):
            for key, value in source.items():
                if key in allowed_keys and isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
                    merged[key] = value
        if set(merged) != allowed_keys:
            scanned = _scan_table_versions(paths['mst_dirs'], paths['loc_dirs'], index_path)
            for key in allowed_keys - set(merged):
                if key in scanned:
                    merged[key] = scanned[key]
        if set(merged) != allowed_keys:
            missing = sorted(k[3:] for k in allowed_keys - set(merged))
            raise ValueError('Cannot sync registry; missing registered table versions: ' + ', '.join(missing[:10]))
        root_elem = ET.Element('map')
        for key in sorted(merged):
            ET.SubElement(root_elem, 'string', {'name': key}).text = merged[key]
        xml_raw = ET.tostring(root_elem, encoding='utf-8', xml_declaration=True)
        _atomic_write(xml_path, xml_raw, readonly=managed)
        modified_files.append(xml_path.relative_to(root_dir).as_posix())
        if registry_path.is_file() or managed:
            reg_raw = (json.dumps(merged, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
            if not registry_path.is_file() or registry_path.read_bytes() != reg_raw:
                _atomic_write(registry_path, reg_raw, readonly=managed)
                modified_files.append(registry_path.relative_to(root_dir).as_posix())
        registry_synced = True

    return {
        'pruned_mst_files': sorted(pruned),
        'reconciled_localized_tables': reconciled,
        'registry_synced': registry_synced,
        'modified_files': sorted(set(modified_files)),
    }


def normalize_managed_stage(stage: Path, files: dict) -> dict:
    """Run compatibility normalization inside a staged managed generation and return updated files."""
    summary = _normalize_directory(stage, managed=True)
    updated = dict(files)
    for rel in summary['pruned_mst_files']:
        updated.pop(rel, None)
    for rel in summary['modified_files']:
        raw = (stage / rel).read_bytes()
        updated[rel] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return updated


def _sync_flat_receipt(data_root: Path, pruned: list[str], modified: list[str]) -> None:
    receipt_path = data_root / '.web_setup/installed.json'
    if not receipt_path.is_file():
        return
    receipt = json.loads(receipt_path.read_bytes())
    files_map = receipt.get('files')
    if isinstance(files_map, dict):
        for rel in pruned:
            files_map.pop(rel, None)
        for rel in modified:
            target = data_root / rel
            if target.is_file():
                raw = target.read_bytes()
                stat_res = target.stat()
                files_map[rel] = {
                    'size': len(raw),
                    'sha256': hashlib.sha256(raw).hexdigest(),
                    'mtime_ns': stat_res.st_mtime_ns,
                }
    pack_files = receipt.get('pack_files')
    if isinstance(pack_files, dict) and pruned:
        pruned_set = set(pruned)
        for pack_id, entries in pack_files.items():
            if isinstance(entries, list):
                pack_files[pack_id] = [item for item in entries if item not in pruned_set]
    raw = (json.dumps(receipt, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    _atomic_write(receipt_path, raw, readonly=False)


def _normalize_published_managed(config) -> dict:
    """Atomically normalize an already-published managed generation without mutating layers."""
    from ios_server import managed_content as content, pack_manifest as policy
    from ios_server.runtime import InstanceLock

    root = config.data_root
    with InstanceLock(config.root), InstanceLock(content.path(root, '.ios-installer')):
        installed = content.load(root, verify=True)
        if installed is None:
            raise ValueError('No managed installation to normalize.')
        report = inspect_directory(installed.directory, managed=True)
        if not report.any_needed and report.error is None:
            return {
                'normalized_now': False,
                'pruned_mst_files': [],
                'reconciled_localized_tables': [],
                'registry_synced': False,
                'modified_files': [],
            }
        parent = content.path(root, content.GENERATIONS)
        stage = Path(tempfile.mkdtemp(prefix='.normalizing-', dir=parent))
        backup = None
        try:
            for rel in installed.record['files']:
                src = content.path(installed.directory, rel)
                dst = stage / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.link(src, dst)
            summary = _normalize_directory(stage, managed=True)
            files = dict(installed.record['files'])
            for rel in summary['pruned_mst_files']:
                files.pop(rel, None)
            for rel in summary['modified_files']:
                raw = (stage / rel).read_bytes()
                files[rel] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            content.verify_files(stage, files)
            content.validate_layout(stage, files)
            record = dict(installed.record, files=files)
            raw_record = policy.encoded(record)
            _atomic_write(stage / 'manifest.json', installed.manifest.raw)
            _atomic_write(stage / 'installation.json', raw_record)
            backup = Path(tempfile.mkdtemp(prefix='.replacing-', dir=parent))
            backup.rmdir()
            os.replace(installed.directory, backup)
            try:
                os.replace(stage, installed.directory)
            except BaseException:
                if not installed.directory.exists() and backup.exists():
                    os.replace(backup, installed.directory)
                raise
            pointer_raw = policy.encoded({
                'version': 1,
                'directory': content.GENERATIONS + '/' + installed.directory.name,
                'installation_sha256': policy.digest(raw_record),
            })
            _atomic_write(content.path(root, content.POINTER), pointer_raw)
            shutil.rmtree(backup)
            return {'normalized_now': True, **summary}
        finally:
            if stage.exists():
                shutil.rmtree(stage)


class DefaultCompatibilityInspector:
    """Default read-only CompatibilityInspector implementation."""

    def inspect(self, config) -> NormalizationReport:
        return inspect_directory(config.content_root, config.managed)


class DefaultCompatibilityNormalizer:
    """Default mutating CompatibilityNormalizer implementation."""

    def normalize(self, config) -> dict:
        from ios_server.update_layouts import detect_layout

        layout = detect_layout(config)
        if layout == 'managed':
            return _normalize_published_managed(config)
        if layout == 'uninstalled':
            return {
                'normalized_now': False,
                'pruned_mst_files': [],
                'reconciled_localized_tables': [],
                'registry_synced': False,
                'modified_files': [],
            }
        from ios_server.runtime import InstanceLock
        with InstanceLock(config.root), InstanceLock(config.data_root / '.ios-installer'):
            report = inspect_directory(config.content_root, managed=False)
            if not report.any_needed and report.error is None:
                return {
                    'normalized_now': False,
                    'pruned_mst_files': [],
                    'reconciled_localized_tables': [],
                    'registry_synced': False,
                    'modified_files': [],
                }
            summary = _normalize_directory(config.content_root, managed=False)
            if summary['pruned_mst_files'] or summary['modified_files']:
                _sync_flat_receipt(config.data_root, summary['pruned_mst_files'], summary['modified_files'])
            return {
                'normalized_now': bool(summary['pruned_mst_files'] or summary['modified_files']),
                **summary,
            }
