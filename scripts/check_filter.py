"""Reproduce the filter and check raw vs unique counts."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app.services.split_service import load_or_build_split, _task_fingerprint

tasks = json.load(open(r'datasets\astra_03_tools.json', 'r', encoding='utf-8'))
split = load_or_build_split(tasks, ratio=0.7, seed=42)

train_fps = set(split.train_fingerprints)
test_fps = set(split.test_fingerprints)
other_fps = set(split.other_fingerprints)
print(f'fps: train={len(train_fps)} test={len(test_fps)} other={len(other_fps)}')
print(f'fp union: {len(train_fps|test_fps|other_fps)} (should == sum if disjoint)')
print(f'train ∩ test: {len(train_fps & test_fps)}')
print(f'train ∩ other: {len(train_fps & other_fps)}')
print(f'test ∩ other: {len(test_fps & other_fps)}')

# Apply filter the same way the runner does
filter_set = test_fps | other_fps
filtered = [t for t in tasks if _task_fingerprint(t) in filter_set]
print(f'\nFiltering with test|other ({len(filter_set)} fps) on {len(tasks)} raw tasks → {len(filtered)} raw kept')

# Tag distribution of the filtered
from collections import Counter
c = Counter(t.get('match_tag') or 'null' for t in filtered)
print('filtered by tag:', dict(c))

# Also check: how many raw tasks have train fingerprints?
train_raw = [t for t in tasks if _task_fingerprint(t) in train_fps]
print(f'\nRaw tasks with TRAIN fingerprints: {len(train_raw)}')
print(f'  (these should be EXCLUDED by the filter)')
c_tag = Counter(t.get('match_tag') or 'null' for t in train_raw)
print('train_raw by tag:', dict(c_tag))
