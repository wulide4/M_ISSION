from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat


class ResultStore:
    def save_payload(self, path: Path, payload: dict[str, np.ndarray]) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {k: np.asarray(v) for k, v in payload.items()}
        np.savez(path, **arrays)
        frame = self._payload_to_frame(arrays)
        frame.to_parquet(path.with_suffix(".parquet"), index=False)
        return str(path)

    def save_series(self, path: Path, time: np.ndarray, values: np.ndarray) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, time=time, values=values)
        frame = self._series_frame(np.asarray(time), np.asarray(values))
        frame.to_parquet(path.with_suffix(".parquet"), index=False)
        return str(path)

    def save_grid(self, path: Path, grid: np.ndarray) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, grid=grid)
        frame = self._grid_frame(np.asarray(grid))
        frame.to_parquet(path.with_suffix(".parquet"), index=False)
        return str(path)

    def save_parquet(self, path: Path, frame: pd.DataFrame) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return str(path)

    def load(self, path: str) -> dict[str, np.ndarray]:
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix == ".npz":
            with np.load(p) as data:
                return {k: data[k] for k in data.files}
        if suffix == ".parquet":
            df = pd.read_parquet(p)
            return {col: df[col].to_numpy() for col in df.columns}
        if suffix == ".json":
            payload = json.loads(p.read_text(encoding="utf-8"))
            return {k: np.asarray(v) for k, v in payload.items()}
        if suffix == ".mat":
            data = loadmat(p, squeeze_me=False, struct_as_record=False)
            return {k: np.asarray(v) for k, v in data.items() if not k.startswith("__")}
        raise ValueError(f"Unsupported result file: {path}")

    def export(self, src_path: str, dst_path: str) -> str:
        src = Path(src_path)
        dst = Path(dst_path)
        dst.parent.mkdir(parents=True, exist_ok=True)

        src_suffix = src.suffix.lower()
        dst_suffix = dst.suffix.lower()
        if src_suffix == dst_suffix:
            shutil.copyfile(src, dst)
            return str(dst)

        payload = self.load(str(src))
        if dst_suffix == ".npz":
            np.savez(dst, **{k: np.asarray(v) for k, v in payload.items()})
            return str(dst)
        if dst_suffix == ".parquet":
            frame = self._payload_to_frame(payload)
            frame.to_parquet(dst, index=False)
            return str(dst)
        if dst_suffix == ".mat":
            savemat(dst, {k: np.asarray(v) for k, v in payload.items()}, do_compression=True)
            return str(dst)
        if dst_suffix == ".json":
            serializable = {k: np.asarray(v).tolist() for k, v in payload.items()}
            dst.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
            return str(dst)
        raise ValueError(f"Unsupported export extension: {dst_suffix}")

    def _series_frame(self, time: np.ndarray, values: np.ndarray) -> pd.DataFrame:
        if values.ndim == 1:
            return pd.DataFrame({"time": time, "value": values})
        if values.ndim == 2:
            frame = pd.DataFrame({"time": time})
            for idx in range(values.shape[1]):
                frame[f"value_{idx:03d}"] = values[:, idx]
            return frame
        flat = values.reshape(values.shape[0], -1)
        frame = pd.DataFrame({"time": time})
        for idx in range(flat.shape[1]):
            frame[f"value_{idx:03d}"] = flat[:, idx]
        return frame

    def _grid_frame(self, grid: np.ndarray) -> pd.DataFrame:
        if grid.ndim == 2:
            d0, d1 = np.indices(grid.shape)
            return pd.DataFrame(
                {
                    "dim0": d0.ravel(),
                    "dim1": d1.ravel(),
                    "value": grid.ravel(),
                }
            )
        if grid.ndim == 3:
            d0, d1, d2 = np.indices(grid.shape)
            return pd.DataFrame(
                {
                    "dim0": d0.ravel(),
                    "dim1": d1.ravel(),
                    "dim2": d2.ravel(),
                    "value": grid.ravel(),
                }
            )
        flat = grid.ravel()
        return pd.DataFrame({"idx": np.arange(flat.size, dtype=int), "value": flat})

    def _payload_to_frame(self, payload: dict[str, np.ndarray]) -> pd.DataFrame:
        arrays = {k: np.asarray(v) for k, v in payload.items()}
        keys = set(arrays.keys())
        if keys == {"time", "values"}:
            return self._series_frame(arrays["time"], arrays["values"])
        if keys == {"grid"}:
            return self._grid_frame(arrays["grid"])

        max_len = max((arr.size for arr in arrays.values()), default=0)
        frame = pd.DataFrame({"row": np.arange(max_len, dtype=int)})
        for key, arr in arrays.items():
            flat = arr.ravel()
            if np.issubdtype(flat.dtype, np.number):
                padded = np.full(max_len, np.nan, dtype=float)
                padded[: flat.size] = flat.astype(float, copy=False)
                frame[key] = padded
            else:
                padded_obj = np.empty(max_len, dtype=object)
                padded_obj[:] = None
                padded_obj[: flat.size] = flat.astype(str, copy=False)
                frame[key] = padded_obj
        return frame
