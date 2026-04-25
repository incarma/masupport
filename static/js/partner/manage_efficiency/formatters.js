// django_ma/static/js/partner/manage_efficiency/formatters.js

export function formatRequesterBranch(user) {
  const grade = user.grade || "";
  const level = (user.level || "").toUpperCase();
  const branch = user.branch || "";
  const teamA = user.team_a || "";
  const teamB = user.team_b || "";
  const teamC = user.team_c || "";
  const part = user.part || "";

  if (grade === "superuser") return part || "-";
  if (grade === "head") return branch || "-";
  if (grade === "leader") {
    if (level === "A") return [teamA].filter(Boolean).join(" + ");
    if (level === "B") return [teamA, teamB].filter(Boolean).join(" + ");
    if (level === "C") return [teamA, teamB, teamC].filter(Boolean).join(" + ");
  }
  return branch || part || "-";
}

export function formatTargetBranch(user) {
  const teamA = user.team_a || "";
  const teamB = user.team_b || "";
  const teamC = user.team_c || "";
  if (teamC) return teamC;
  if (teamB) return [teamB, teamC].filter(Boolean).join(" + ");
  if (teamA) return [teamA, teamB, teamC].filter(Boolean).join(" + ");
  return user.branch || "-";
}
