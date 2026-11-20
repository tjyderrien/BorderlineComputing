# Useful when Scholar Google fails to load due to IP v4,v6 conflict. 
# disable_ipv6=1 turns IPv6 off; =0 turns it back on.
sudo sysctl -w net.ipv6.conf.wlan0.disable_ipv6=1
