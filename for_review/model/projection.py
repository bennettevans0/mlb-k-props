import statistics


def project_ks(
    k_per9: float,
    recent_ip: list[float],
    opp_k_rate: float,
    league_k_rate: float,
) -> tuple[float, float]:
    if not recent_ip:
        return 0.0, 0.0

    median_ip = statistics.median(recent_ip)
    opp_factor = opp_k_rate / league_k_rate if league_k_rate > 0 else 1.0
    projected_ks = (k_per9 / 9) * median_ip * opp_factor

    if len(recent_ip) >= 2:
        per_start = [(k_per9 / 9) * ip for ip in recent_ip]
        std_dev = statistics.stdev(per_start)
    else:
        std_dev = projected_ks * 0.25

    std_dev = max(std_dev, 0.5)
    return projected_ks, std_dev
