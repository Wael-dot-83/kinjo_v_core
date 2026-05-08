"""
Manual test for anomaly detection logic
"""
from data_quality_manager import DataQualityManager

series = [10, 12, 11, 50]
print("mean:", sum(series)/len(series))
import numpy as np
arr = np.array(series)
mean = arr.mean()
std = arr.std()
print("std:", std)
for i, v in enumerate(arr):
    print(f"{i}: {v}, z={(v-mean)/std if std else 0}")
print("anomalies:", DataQualityManager.detect_anomalies(series, threshold=2.0))
print("anomalies (thresh=1.5):", DataQualityManager.detect_anomalies(series, threshold=1.5))
