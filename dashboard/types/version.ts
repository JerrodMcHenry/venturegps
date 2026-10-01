export interface PlatformVersion {
  app: string;
  version: string;
  methodology_version: string;
  // Task 33 item 2 -- the server-authoritative signal for whether
  // Evidence v1 is enabled. This is a read of CURRENT STATE only -- it
  // never authorizes a request on its own; POST /analyze's own
  // server-side resolve_engine() independently re-checks this every
  // time, regardless of what the client believes.
  evidence_v1_enabled: boolean;
}
