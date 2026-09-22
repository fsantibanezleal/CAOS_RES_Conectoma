"""Tests for the vision data lane (unit U4): fetching members, decoding, the eye, contract 1, splits.

Everything runs offline. The remote-ZIP reader is exercised against a local HTTP server that honours range
requests, the decoders against frames encoded the way the release encodes them, the renderer against the
engine's own BoxEye, and the split rule against its leakage test. Nothing here writes a canonical artifact.
"""

from __future__ import annotations

import http.server
import io
import re
import sys
import threading
import zipfile
import zlib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data-pipeline"))

from conectoma.stages.vision_data import load_config  # noqa: E402
from conectoma.vision import contract, decode, eye, splits, tartanair  # noqa: E402
from conectoma.vision.remote_zip import RemoteZip  # noqa: E402

# ---------------------------------------------------------------------------------------------------------
# remote ZIP over HTTP ranges


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    payload = b""

    def log_message(self, *args):  # silence the test server
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        match = re.match(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
        if not match:
            self.send_response(200)
            self.send_header("Content-Length", str(len(self.payload)))
            self.end_headers()
            self.wfile.write(self.payload)
            return
        start, end = int(match[1]), min(int(match[2]), len(self.payload) - 1)
        body = self.payload[start: end + 1]
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {start}-{end}/{len(self.payload)}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def served_zip():
    members = {f"env/Data_easy/P000/image_lcam_front/{i:06d}_lcam_front.png": bytes([i]) * (1000 + 37 * i)
               for i in range(40)}
    members["env/Data_easy/P000/stored.bin"] = b"stored" * 100
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            method = zipfile.ZIP_STORED if name.endswith(".bin") else zipfile.ZIP_DEFLATED
            archive.writestr(name, data, compress_type=method)
    handler = type("Handler", (_RangeHandler,), {"payload": buffer.getvalue()})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/archive.zip", members, handler
    server.shutdown()


def test_remote_zip_lists_and_reads_members_exactly(served_zip):
    url, members, _ = served_zip
    archive = RemoteZip(url)
    assert archive.names() == sorted(members)
    for name in list(members)[::7] + ["env/Data_easy/P000/stored.bin"]:
        assert archive.read(name) == members[name]


def test_remote_zip_refuses_a_corrupt_member(served_zip):
    url, members, handler = served_zip
    archive = RemoteZip(url)
    name = sorted(members)[3]
    member = archive.members[name]
    # flip one byte inside the member's compressed data on the server
    payload = bytearray(handler.payload)
    payload[member.header_offset + 30 + len(name) + 2] ^= 0xFF
    handler.payload = bytes(payload)
    with pytest.raises((OSError, zlib.error)):
        archive.read(name)


def test_remote_zip_writes_atomically(served_zip, tmp_path):
    url, members, _ = served_zip
    archive = RemoteZip(url)
    name = sorted(members)[0]
    target = tmp_path / "out" / "frame.png"
    assert archive.fetch(name, target) == len(members[name])
    assert target.read_bytes() == members[name]
    assert not list(tmp_path.rglob("*.partial"))


# ---------------------------------------------------------------------------------------------------------
# the clip rule


def _names(trajectory: str, n: int) -> list[str]:
    return [f"Env/Data_easy/{trajectory}/image_lcam_front/{i:06d}_lcam_front.png" for i in range(n)]


def test_clips_are_disjoint_and_centred():
    names = _names("P000", 200) + _names("P001", 40) + _names("P002", 20)
    clips = tartanair.plan_clips(names, 32, [0.25, 0.75])
    by_trajectory = {}
    for clip in clips:
        by_trajectory.setdefault(clip.trajectory, []).append(clip)
    assert [c.start for c in by_trajectory["P000"]] == [34, 134]     # centred at 50 and 150
    assert [c.start for c in by_trajectory["P001"]] == [4]           # too short for two: one, in the middle
    assert "P002" not in by_trajectory                               # shorter than a clip: nothing
    for group in by_trajectory.values():
        frames = [f for c in group for f in c.frames()]
        assert len(frames) == len(set(frames))


def test_a_trajectory_with_a_gap_is_not_planned():
    names = _names("P000", 100)
    del names[50]
    assert tartanair.plan_clips(names, 32, [0.25, 0.75]) == []


def test_clip_members_cover_every_modality():
    clip = tartanair.Clip("Env", "easy", "P000", 10, 32, 200)
    members = tartanair.clip_members(clip, "lcam_front")
    assert len(members["image"]) == 33 and members["image"][-1].endswith("pose_lcam_front.txt")
    assert len(members["depth"]) == len(members["seg"]) == 32
    assert len(members["flow"]) == 31 and members["flow"][0].endswith("000010_000011_flow.png")


# ---------------------------------------------------------------------------------------------------------
# decoders and the pose convention


def test_depth_and_flow_decode_as_the_reference_encodes(tmp_path):
    import cv2

    depth = np.random.default_rng(0).uniform(0.3, 80, (48, 64)).astype(np.float32)
    cv2.imwrite(str(tmp_path / "d.png"), depth.view(np.uint8).reshape(48, 64, 4))
    assert np.array_equal(decode.tartanair_depth(tmp_path / "d.png"), depth)

    flow = np.random.default_rng(1).uniform(-40, 40, (2, 48, 64)).astype(np.float32)
    flow = np.round(flow * 64) / 64                                   # the format's resolution
    mask = np.where(np.random.default_rng(2).random((48, 64)) < 0.1, 100, 0).astype(np.uint16)
    encoded = np.dstack([flow[0] * 64 + 32768, flow[1] * 64 + 32768, mask]).astype(np.uint16)
    cv2.imwrite(str(tmp_path / "f.png"), encoded)
    decoded, decoded_mask = decode.tartanair_flow(tmp_path / "f.png")
    assert np.array_equal(decoded, flow) and np.array_equal(decoded_mask, mask.astype(np.uint8))


def test_reprojected_flow_of_a_known_motion():
    # a camera moving 0.5 m forward in NED (x forward) toward a wall 10 m away: pure expansion from the centre
    pose_a = np.array([0, 0, 0, 0, 0, 0, 1.0])
    pose_b = np.array([0.5, 0, 0, 0, 0, 0, 1.0])
    rotation, translation = decode.relative_motion(pose_a, pose_b)
    assert np.allclose(rotation, np.eye(3)) and np.allclose(translation, [0, 0, -0.5])
    depth = np.full((9, 9), 10.0)
    flow = decode.flow_from_depth(depth, rotation, translation, 100.0, 100.0, 4.0, 4.0)
    assert np.allclose(flow[:, 4, 4], 0)                              # the focus of expansion stays put
    assert flow[0, 4, 8] > 0 and flow[1, 8, 4] > 0                    # right moves right, bottom moves down
    assert np.isclose(flow[0, 4, 8], 4 * (10 / 9.5 - 1))


# ---------------------------------------------------------------------------------------------------------
# the eye, against the engine's BoxEye


def test_the_eye_matches_boxeye():
    pytest.importorskip("flyvis")
    import torch
    from flyvis.datasets.rendering.eye import BoxEye
    from flyvis.utils.hex_utils import get_hex_coords

    # BoxEye works on the engine's default device (CUDA where there is one, CPU in CI)
    box = BoxEye(extent=15, kernel_size=13)
    frames = np.random.default_rng(3).random((1, 2, 420, 400)).astype(np.float32)
    tensor = torch.tensor(frames)

    def run(ftype):
        return box(tensor, ftype=ftype).cpu().numpy()[:, :, 0]

    assert np.array_equal(box.receptor_centers.cpu().numpy(), eye.receptor_centers())
    u, v = get_hex_coords(15)
    assert np.array_equal(np.stack([u, v], 1), eye.lattice_coordinates())
    assert np.allclose(run("mean"), eye.box_mean(frames), atol=1e-6)
    assert np.allclose(run("sum"), eye.box_sum(frames), atol=1e-4)
    assert np.array_equal(run("median"), eye.box_median(frames))


def test_the_lattice_window_is_391_pixels_square():
    assert eye.min_frame_size() == (391, 391)
    assert len(eye.receptor_centers()) == 721


def test_box_targets():
    labels = np.zeros((60, 60), dtype=np.uint8)
    labels[:, 30:] = 7                                                # a vertical edge through the centre
    distinct = eye.box_distinct(labels, extent=1, kernel=5)
    assert distinct.max() == 2 and distinct.min() == 1
    share = eye.box_share(labels == 7, extent=0, kernel=5)
    # the one column sits at pixel 30; its box spans 28 to 32, and 30, 31 and 32 are on the labelled side
    assert np.isclose(share[0], 0.6)


# ---------------------------------------------------------------------------------------------------------
# contract 1


def _clip(n=4, columns=contract.COLUMNS):
    rng = np.random.default_rng(4)
    return {
        "lum": rng.random((n, columns), dtype=np.float32),
        "depth": rng.uniform(0.5, 30, (n, columns)).astype(np.float32),
        "flow": rng.normal(0, 1, (n - 1, 2, columns)).astype(np.float32),
        "flow_valid": rng.random((n - 1, columns), dtype=np.float32),
        "boundary": (rng.random((n, columns)) < 0.2).astype(np.uint8),
        "poses": np.tile([0, 0, 0, 0, 0, 0, 1.0], (n, 1)),
        "frames": np.arange(10, 10 + n, dtype=np.int32),
    }


def test_a_valid_clip_holds_the_contract():
    assert contract.clip_problems(_clip()) == []


@pytest.mark.parametrize("breakage, expected", [
    (lambda c: c["lum"].__setitem__((0, 0), 1.5), "luminance"),
    (lambda c: c["depth"].__setitem__((1, 1), 0.0), "non-positive"),
    (lambda c: c["depth"].__setitem__((1, 1), np.inf), "infinite"),
    (lambda c: c["flow"].__setitem__((0, 0, 0), np.nan), "flow is not finite"),
    (lambda c: c["flow_valid"].__setitem__((0, 0), -0.1), "flow_valid"),
    (lambda c: c["boundary"].__setitem__((0, 0), 3), "binary"),
    (lambda c: c["poses"].__setitem__((0, 6), 2.0), "unit quaternions"),
    (lambda c: c["frames"].__setitem__(2, 99), "consecutive"),
    (lambda c: c["lum"].__setitem__(1, 0.0), "blank frames"),
])
def test_each_breakage_is_rejected_with_its_reason(breakage, expected):
    clip = _clip()
    breakage(clip)
    assert any(expected in problem for problem in contract.clip_problems(clip))


def test_only_a_synthetic_scene_may_be_blank():
    clip = _clip()
    clip["lum"][:] = 0.5                       # uniform grey, as C16 at zero texture contrast
    del clip["boundary"], clip["poses"]
    assert contract.clip_problems(clip, "synthetic") == []
    assert any("blank" in p for p in contract.clip_problems({**_clip(), "lum": clip["lum"]}, "tartanair"))


def test_masked_depth_is_allowed():
    clip = _clip()
    clip["depth"][0, :10] = np.nan
    assert contract.clip_problems(clip) == []


# ---------------------------------------------------------------------------------------------------------
# splits by geometry family


@pytest.fixture(scope="module")
def vision_config():
    config, _ = load_config()
    return config


@pytest.fixture(scope="module")
def environments(vision_config):
    index = tartanair.read_index(ROOT / "data-pipeline" / "config" / vision_config["tartanair"]["index"])
    return sorted({env for env, _, _, _ in index})


def test_the_index_covers_every_environment_four_ways(vision_config, environments):
    index = tartanair.read_index(ROOT / "data-pipeline" / "config" / vision_config["tartanair"]["index"])
    assert len(environments) == 74
    assert len(index) == 74 * 2 * 4


def test_relit_and_reseasoned_environments_share_a_family(vision_config, environments):
    family = splits.family_of(vision_config, environments)
    assert len({family[e] for e in ("OldTownFall", "OldTownNight", "OldTownSummer", "OldTownWinter")}) == 1
    assert family["ArchVizTinyHouseDay"] == family["ArchVizTinyHouseNight"]
    assert family["Downtown"] == "Downtown"
    assert len(set(family.values())) == 60


def test_the_assignment_is_deterministic_and_keeps_case_families_in_test(vision_config, environments):
    first = splits.assign(vision_config, environments)
    assert first == splits.assign(vision_config, environments)
    for case_family in vision_config["splits"]["case_families"]:
        assert first[case_family] == "test"
    assert set(first.values()) == set(splits.SPLITS)


def test_the_leakage_test_catches_a_family_split_by_name(vision_config, environments):
    family = splits.family_of(vision_config, environments)
    split_of_family = splits.assign(vision_config, environments)
    rows = [{"key": "a", "environment": "OldTownFall", "split": split_of_family["OldTown"]},
            {"key": "b", "environment": "OldTownNight", "split": split_of_family["OldTown"]}]
    assert splits.leakage_problems(rows, family, split_of_family) == []
    other = next(s for s in splits.SPLITS if s != split_of_family["OldTown"])
    rows[1]["split"] = other                                          # what a split by name would do
    problems = splits.leakage_problems(rows, family, split_of_family)
    assert any("family OldTown" in p for p in problems)


def test_the_leakage_test_catches_an_identical_frame(vision_config, environments):
    family = splits.family_of(vision_config, environments)
    split_of_family = splits.assign(vision_config, environments)
    train = next(e for e in environments if split_of_family[family[e]] == "train")
    test = next(e for e in environments if split_of_family[family[e]] == "test")
    rows = [{"key": "a", "environment": train, "split": "train"},
            {"key": "b", "environment": test, "split": "test"}]
    digests = {"a": ["same", "x"], "b": ["same", "y"]}
    problems = splits.leakage_problems(rows, family, split_of_family, digests)
    assert any("identical frames" in p for p in problems)
