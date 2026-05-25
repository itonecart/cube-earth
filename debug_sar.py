
import asyncio, sys, struct, math
sys.path.insert(0, "/workspaces/cube-earth")
from extractors.opera_s1_extractor import OPERAS1Extractor
from config.settings import settings
import httpx

async def main():
    s1 = OPERAS1Extractor()
    raw = await s1.extract(53.71, -6.29, "2026-04-01", "2026-05-25")
    url = raw["links"]["vv"]
    lat, lng = 53.71, -6.29
    headers = {"Authorization": f"Bearer {settings.NASA_TOKEN}"}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(url, headers={**headers, "Range": "bytes=0-65535"})
        buf = r.content
        le = buf[0] == 0x49
        fmt = "<" if le else ">"
        ifd_off = struct.unpack_from(f"{fmt}I", buf, 4)[0]
        n = struct.unpack_from(f"{fmt}H", buf, ifd_off)[0]
        tags = {}
        for i in range(n):
            off = ifd_off + 2 + i*12
            if off+12>len(buf): break
            tag = struct.unpack_from(f"{fmt}H", buf, off)[0]
            val = struct.unpack_from(f"{fmt}I", buf, off+8)[0]
            tags[tag] = val
        w = tags.get(256,0)
        h = tags.get(257,0)
        sc_x = struct.unpack_from(f"{fmt}d", buf, tags[33550])[0]
        sc_y = struct.unpack_from(f"{fmt}d", buf, tags[33550]+8)[0]
        tie_x = struct.unpack_from(f"{fmt}d", buf, tags[33922]+24)[0]
        tie_y = struct.unpack_from(f"{fmt}d", buf, tags[33922]+32)[0]
        print(f"Image: {w}x{h} Scale: {sc_x}m")
        print(f"Tie: E={tie_x:.0f} N={tie_y:.0f}")
        print(f"Covers E={tie_x:.0f} to {tie_x+w*sc_x:.0f}")
        print(f"Covers N={tie_y-h*sc_y:.0f} to {tie_y:.0f}")
        zone = int((lng+180)/6)+1
        lon0 = math.radians((zone-1)*6-180+3)
        phi,lam = math.radians(lat),math.radians(lng)
        a,e2,k0 = 6378137.0,0.00669438,0.9996
        N2 = a/math.sqrt(1-e2*math.sin(phi)**2)
        T = math.tan(phi)**2
        C = (e2/(1-e2))*math.cos(phi)**2
        A2 = math.cos(phi)*(lam-lon0)
        M = a*((1-e2/4-3*e2**2/64)*phi-(3*e2/8+3*e2**2/32)*math.sin(2*phi))
        E = k0*N2*(A2+(1-T+C)*A2**3/6)+500000
        Np = k0*(M+N2*math.tan(phi)*(A2**2/2+(5-T+9*C)*A2**4/24))
        px = int((E-tie_x)/sc_x)
        py = int((tie_y-Np)/sc_y)
        print(f"UTM zone={zone} E={E:.0f} N={Np:.0f}")
        print(f"Pixel px={px} py={py} inside={0<=px<w and 0<=py<h}")

asyncio.run(main())
