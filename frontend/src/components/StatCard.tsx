interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: "blue" | "red" | "green" | "gray";
}

const colorMap = {
  blue: "text-blue-600",
  red: "text-red-500",
  green: "text-green-600",
  gray: "text-gray-600",
};

export default function StatCard({
  label,
  value,
  sub,
  color = "gray",
}: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </span>
      <span className={`text-3xl font-bold ${colorMap[color]}`}>{value}</span>
      {sub && <span className="text-xs text-gray-400">{sub}</span>}
    </div>
  );
}
