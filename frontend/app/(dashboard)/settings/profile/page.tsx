import { serverFetch } from "@/lib/auth-action";
import type { CurrentUser } from "@/types";

const ROLE_LABELS: Record<CurrentUser["role"], string> = {
  super_admin: "Super Admin",
  hiring_manager: "Hiring Manager",
  interviewer: "Interviewer",
};

export default async function ProfilePage() {
  let user: CurrentUser | null = null;
  try {
    const res = await serverFetch<{ data: CurrentUser }>("/users/me");
    user = res.data;
  } catch {
    return <p className="p-6 text-neutral-500">You are not signed in.</p>;
  }

  const fullName = `${user.firstName} ${user.lastName}`.trim();
  const roleLabel = ROLE_LABELS[user.role];

  return (
    <div className="w-full px-8 py-8">
      <div className="mb-8">
        <h1 className="text-lg font-medium text-neutral-900 dark:text-white">
          My Profile
        </h1>
        <p className="text-sm text-neutral-500 mt-0.5">
          Your account information.
        </p>
      </div>

      {/* Avatar card */}
      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-xl p-6 mb-4">
        <div className="flex items-center gap-5">
          {user.avatarUrl ? (
            <img
              src={user.avatarUrl}
              alt={fullName}
              className="w-16 h-16 rounded-full object-cover flex-shrink-0"
            />
          ) : (
            <div className="w-16 h-16 rounded-full bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center text-neutral-600 dark:text-neutral-300 text-xl font-medium flex-shrink-0">
              {fullName.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="text-base font-medium text-neutral-900 dark:text-white">
              {fullName}
            </p>
            <p className="text-sm text-neutral-500 mt-0.5">{user.email}</p>
            <div className="flex gap-1.5 mt-2 flex-wrap">
              <span className="text-xs px-2 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700">
                {roleLabel}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Personal info */}
      <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-xl overflow-hidden">
        <div className="px-6 py-3.5 border-b border-neutral-100 dark:border-neutral-800">
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wider">
            Personal information
          </p>
        </div>
        <ProfileRow label="Full name" value={fullName} />
        <ProfileRow label="Email address" value={user.email} />
        <ProfileRow label="Role" value={roleLabel} last />
      </div>
    </div>
  );
}

function ProfileRow({
  label,
  value,
  last = false,
}: {
  label: string;
  value?: string | null;
  last?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between px-6 py-4 ${!last ? "border-b border-neutral-100 dark:border-neutral-800" : ""}`}
    >
      <p className="text-sm text-neutral-500 dark:text-neutral-400 w-40 flex-shrink-0">
        {label}
      </p>
      <p className="text-sm text-neutral-900 dark:text-neutral-100 text-right">
        {value ?? <span className="text-neutral-400">—</span>}
      </p>
    </div>
  );
}
