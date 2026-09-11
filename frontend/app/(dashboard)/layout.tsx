import { Suspense } from "react";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { SiteHeader } from "@/components/layout/site-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { DragDropProvider } from "@/components/dynamic-imports";
import { PrefetchProvider } from "@/components/providers/prefetch-provider";
import { CandidateSocketProvider } from "@/components/providers/candidate-socket-provider";
import { SocketAuthProvider } from "@/components/providers/socket-auth-provider";
import { getSessionToken } from "@/lib/session";
import { SetupCompanyGate } from "@/components/guards/setup-company-gate";
import { QueryProvider } from "@/components/providers/query-provider";
import { Toaster } from "@/components/ui/sonner";
import { DashboardMainLoading } from "@/components/dashboard-main-loading";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const socketToken = await getSessionToken();

  return (
    <QueryProvider>
      <SocketAuthProvider token={socketToken}>
        <PrefetchProvider />
        <CandidateSocketProvider />
        <div className="[--header-height:calc(--spacing(14))]">
          <SidebarProvider className="flex flex-col">
            <SiteHeader />
            <div className="flex flex-1 min-w-0 overflow-x-hidden w-full">
              <AppSidebar />
              <SidebarInset>
                <DragDropProvider>
                  <SetupCompanyGate>
                    <Suspense fallback={<DashboardMainLoading />}>
                      {children}
                    </Suspense>
                  </SetupCompanyGate>
                </DragDropProvider>
              </SidebarInset>
            </div>
          </SidebarProvider>
        </div>
        <Toaster richColors closeButton />
      </SocketAuthProvider>
    </QueryProvider>
  );
}
