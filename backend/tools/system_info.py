"""VNSA 2.0 — System info."""
import platform
import sys
from datetime import datetime

TOOL_DEFINITION = {
    "name": "system_info",
    "description": "Get system information: time, date, battery, CPU/RAM, processes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "enum": ["time", "date", "datetime", "battery",
                               "cpu", "ram", "disk", "processes", "all"]}
        },
        "required": ["query"],
    },
}


def run(query: str = "datetime") -> str:
    import psutil
    now = datetime.now()

    if query in ("time", "datetime", "date"):
        return now.strftime("%A, %d %B %Y — %H:%M:%S")

    if query == "battery":
        b = psutil.sensors_battery()
        if not b:
            return "No battery detected (desktop)."
        status = "charging" if b.power_plugged else "on battery"
        return f"Battery: {b.percent:.0f}% ({status})"

    if query == "cpu":
        return f"CPU usage: {psutil.cpu_percent(interval=1)}% — {psutil.cpu_count()} cores"

    if query == "ram":
        r = psutil.virtual_memory()
        return (f"RAM: {r.used / 1e9:.1f} GB used / "
                f"{r.total / 1e9:.1f} GB total ({r.percent:.0f}%)")

    if query == "disk":
        d = psutil.disk_usage("/")
        return (f"Disk: {d.used / 1e9:.1f} GB used / "
                f"{d.total / 1e9:.1f} GB total ({d.percent:.0f}%)")

    if query == "processes":
        procs = sorted(psutil.process_iter(["name", "cpu_percent"]),
                       key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:5]
        lines = ["Top processes:"]
        for p in procs:
            lines.append(f"  {p.info['name']} — {p.info['cpu_percent']:.1f}%")
        return "\n".join(lines)

    if query == "all":
        b    = psutil.sensors_battery()
        batt = f"{b.percent:.0f}% ({'charging' if b.power_plugged else 'battery'})" if b else "N/A"
        r    = psutil.virtual_memory()
        return (f"{now.strftime('%A %d %B %Y, %H:%M')}\n"
                f"Battery: {batt}\n"
                f"CPU: {psutil.cpu_percent(interval=0.5):.0f}%  "
                f"RAM: {r.percent:.0f}%\n"
                f"OS: {platform.system()} {platform.release()}")

    return f"Unknown query: {query}"
