"""Authored positions and actual raster pixels, independent of the LOD producer."""

import hashlib
import struct
import sys
from pathlib import Path

from PIL import Image

from xyg._graphforge_container import decode_container
from xyg._temporal_graph_frozen import FrozenTemporalGraph


def verify(directory):
    expected = [[30, 131], [30.5, 130.5], [30, 130.5], [30, 131], [30], [30.5, 130.5]]
    for i, centers in enumerate(expected):
        m = decode_container((directory / f"frame-{i}.xyfg").read_bytes()[:-8], "XYFG")
        p = decode_container(m["render.publication", 0], "XYGR")
        # Camera and author x/y, not retained paint, determine expected centers.
        actual = list(p["paint.node.center.f64", 0])
        assert actual == [v for x in centers for v in (x, 60)]
        for suffix in ("png", "offline.png", "live"):
            image_path = directory / (
                f"live-{i}.png" if suffix == "live" else f"frame-{i}.{suffix}"
            )
            image = Image.open(image_path).convert("RGBA")

            def check(candidate, centers=centers, i=i, suffix=suffix):
                for x in centers:
                    pixel = candidate.getpixel((round(x), 60))
                    assert pixel[3] > 0 and min(pixel[:3]) < 240, (i, suffix, x, pixel)
                if i == 4:
                    pixel = candidate.getpixel((131, 60))
                    assert pixel[3] == 0 or min(pixel[:3]) >= 240

            check(image)
            # A shift and the hidden-frame's stale previous picture must fail.
            from PIL import ImageChops

            shifted = ImageChops.offset(image, 25, 20)
            try:
                check(shifted)
            except AssertionError:
                pass
            else:
                raise AssertionError("shifted visual negative control passed")
            if i == 4:
                try:
                    check(
                        Image.open(
                            directory / ("live-3.png" if suffix == "live" else f"frame-3.{suffix}")
                        ).convert("RGBA")
                    )
                except AssertionError:
                    pass
                else:
                    raise AssertionError("stale visual negative control passed")
    # Mutate genuine snapshots, recompute their integrity digest, and require
    # semantic validation to refuse duplicated/missing/stale membership.
    raw = (directory / "frame-1.xyfg").read_bytes()

    def section(data, wanted):
        count = struct.unpack_from("<I", data, 8)[0]
        names = 32 + count * 40
        for row in range(count):
            at = 32 + row * 40
            name_at, name_len = struct.unpack_from("<II", data, at)
            if data[names + name_at : names + name_at + name_len].decode() == wanted:
                return struct.unpack_from("<QQQ", data, at + 16)
        raise AssertionError(wanted)

    outer, _, length = section(raw, "render.publication")
    publication = raw[outer : outer + length]
    at, _, _ = section(publication, "render.node_members.u64")
    offset, _, _ = section(publication, "render.node_member_offsets.u64")
    for label, position, value in (
        ("duplicated", at + 8, 0),
        ("stale", at + 8, 3),
        ("missing", offset + 16, 3),
    ):
        bad = bytearray(raw[:-8])
        struct.pack_into("<Q", bad, outer + position, value)
        digest = hashlib.blake2s(
            b"xyg-frozen-temporal-v2" + bad, digest_size=8, person=b"xykeyv1"
        ).digest()
        try:
            accepted = FrozenTemporalGraph.from_bytes(bytes(bad) + digest)
        except ValueError:
            pass
        else:
            accepted.close()
            raise AssertionError(f"{label} membership accepted")
    print("Authored centers, raster/offline pixels, shifted/stale visual controls passed")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
