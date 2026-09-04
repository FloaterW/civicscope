import { ImageResponse } from "next/og";

export const socialImageSize = {
  width: 1200,
  height: 630
};

export function createSocialImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#f5f7f4",
          color: "#18212f",
          padding: "62px 68px",
          fontFamily: "sans-serif"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <svg width="58" height="58" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="#0b6864" />
            <path
              d="M7.5 9.6 13 7.4l6 2.2 5.5-2.2v14.9L19 24.5l-6-2.2-5.5 2.2Z"
              fill="none"
              stroke="#fff"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.6"
            />
            <path
              d="M13 7.4v14.9m6-12.7v6.1"
              fill="none"
              stroke="#fff"
              strokeLinecap="round"
              strokeWidth="1.35"
              opacity="0.8"
            />
            <circle cx="18.4" cy="17.6" r="3.25" fill="#0b6864" stroke="#fff" strokeWidth="1.6" />
            <path d="m20.8 20 2.6 2.6" fill="none" stroke="#fff" strokeLinecap="round" strokeWidth="1.7" />
          </svg>
          <div style={{ display: "flex", fontSize: 25, fontWeight: 700, letterSpacing: 2.2, color: "#0b6864" }}>
            CIVICSCOPE
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 56 }}>
          <div style={{ width: 610, display: "flex", flexDirection: "column", gap: 26 }}>
            <div style={{ display: "flex", flexDirection: "column", fontSize: 62, lineHeight: 1.03, fontWeight: 750, letterSpacing: -2.2 }}>
              <span>GTA Housing</span>
              <span>Affordability Explorer</span>
            </div>
            <div style={{ display: "flex", width: 570, fontSize: 25, lineHeight: 1.42, color: "#4f5b6b" }}>
              Explore rent burden, income, housing supply, and transit access across the Greater Toronto Area.
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {[
                "25 municipalities",
                "1,334 census tracts",
                "Census + CMHC + transit"
              ].map((label) => (
                <div
                  key={label}
                  style={{
                    display: "flex",
                    border: "1px solid #c7d1d8",
                    borderRadius: 8,
                    background: "#ffffff",
                    padding: "9px 14px",
                    fontSize: 17,
                    color: "#4f5b6b"
                  }}
                >
                  {label}
                </div>
              ))}
            </div>
          </div>

          <div
            style={{
              width: 420,
              height: 350,
              display: "flex",
              flexDirection: "column",
              border: "1px solid #c7d1d8",
              borderRadius: 18,
              background: "#ffffff",
              boxShadow: "0 18px 44px rgba(24,33,47,0.12)",
              overflow: "hidden"
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 22px", borderBottom: "1px solid #d8dee6" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <span style={{ fontSize: 19, fontWeight: 700 }}>Rent burden</span>
                <span style={{ fontSize: 14, color: "#4f5b6b" }}>By census tract</span>
              </div>
              <span style={{ display: "flex", border: "1px solid #d8dee6", borderRadius: 7, padding: "5px 9px", fontSize: 13, color: "#4f5b6b" }}>Census 2021</span>
            </div>
            <div style={{ display: "flex", flex: 1, padding: 18, background: "#eef3ef" }}>
              <svg width="384" height="224" viewBox="0 0 384 224" aria-hidden="true">
                <path d="M18 72 88 24l61 27-10 72-82 27-39-31Z" fill="#e8f2ed" stroke="#fff" strokeWidth="3" />
                <path d="m88 24 95 4 39 55-83 40 10-72Z" fill="#8cc9bb" stroke="#fff" strokeWidth="3" />
                <path d="m183 28 89 21 28 70-78-36Z" fill="#2e8471" stroke="#fff" strokeWidth="3" />
                <path d="m57 150 82-27 76 45-48 43-104-8Z" fill="#68b7aa" stroke="#fff" strokeWidth="3" />
                <path d="m139 123 83-40 78 36-27 76-58-27Z" fill="#a64822" stroke="#fff" strokeWidth="3" />
                <path d="m300 119 66 22-18 67-75-13Z" fill="#d8dee6" stroke="#fff" strokeWidth="3" />
                <circle cx="235" cy="137" r="9" fill="#ffffff" stroke="#18212f" strokeWidth="4" />
              </svg>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "13px 20px", borderTop: "1px solid #d8dee6", color: "#4f5b6b", fontSize: 13 }}>
              <span style={{ display: "flex", width: 12, height: 12, borderRadius: 3, background: "#e8f2ed" }} />
              Lower
              <span style={{ display: "flex", width: 12, height: 12, marginLeft: 8, borderRadius: 3, background: "#a64822" }} />
              Higher
              <span style={{ display: "flex", width: 12, height: 12, marginLeft: 8, borderRadius: 3, background: "#d8dee6" }} />
              No data
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "#4f5b6b", fontSize: 17 }}>
          <span>Official sources · transparent estimates · shareable views</span>
          <span style={{ color: "#0b6864", fontWeight: 700 }}>civicscope-gold.vercel.app</span>
        </div>
      </div>
    ),
    socialImageSize
  );
}
