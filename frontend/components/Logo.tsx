export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <span style={{ width: size + 10, height: size + 10, display: "grid", placeItems: "center" }}>
      <span style={{ width: size, height: size, background: "#7c6cf0", borderRadius: 5, transform: "rotate(45deg)", display: "grid", placeItems: "center" }}>
        <span style={{ width: Math.round(size * 0.36), height: Math.round(size * 0.36), background: "#3ee6c0", borderRadius: "50%" }} />
      </span>
    </span>
  );
}
