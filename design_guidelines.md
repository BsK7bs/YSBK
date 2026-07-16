{
  "product": {
    "name": "Digital Twin Platform",
    "type": "enterprise_saas_device_monitoring",
    "design_personality": {
      "attributes": [
        "premium",
        "calm under pressure",
        "high-signal / low-noise",
        "trustworthy",
        "fast and data-dense without feeling cramped",
        "operator-first"
      ],
      "visual_metaphor": "Mission-control console: dark, quiet surfaces + crisp typography + precise status color semantics + subtle motion that communicates liveness.",
      "north_star": "Feels like Linear/Vercel polish with Datadog/Grafana information density—never like a template."
    }
  },

  "global_rules": {
    "mobile_first": true,
    "default_theme": "dark",
    "light_mode_toggle": true,
    "radius_target_px": "12–16",
    "glassmorphism_scope": "ONLY modals/dialogs/sheets (not cards, not tables, not main surfaces)",
    "no_mock_data": "If DB is empty, show premium empty states with CTA.",
    "data_testid_requirement": "All interactive and key informational elements MUST include data-testid (kebab-case, role-based).",
    "do_not_change_api_contracts": true
  },

  "inspiration_fusion": {
    "layout_principles": [
      "Datadog-style 12-col dashboard grid + grouped sections",
      "Linear-style sidebar density + crisp typography",
      "Vercel-style topbar search + command palette",
      "Grafana-style time range controls + live refresh affordances"
    ],
    "notes": [
      "Use a strict 8px spacing rhythm; increase whitespace 2–3x vs instinct.",
      "Use subtle 1px borders with white alpha (5–10%) on dark surfaces.",
      "Use motion to communicate real-time updates (pulses, shimmer, count-up), not decoration."
    ]
  },

  "image_urls": {
    "hero_or_auth_backgrounds": [
      {
        "url": "https://images.unsplash.com/photo-1557683316-973673baf926?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjd8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMGRhcmslMjBibHVlJTIwZ3JhZGllbnQlMjBtZXNoJTIwYmFja2dyb3VuZCUyMHN1YnRsZXxlbnwwfHx8Ymx1ZXwxNzgzODk3NzcyfDA&ixlib=rb-4.1.0&q=85",
        "category": "auth",
        "description": "Subtle blue mesh gradient for auth page header band (max 20% viewport)."
      },
      {
        "url": "https://images.unsplash.com/photo-1557683304-673a23048d34?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjd8MHwxfHNlYXJjaHwyfHxhYnN0cmFjdCUyMGRhcmslMjBibHVlJTIwZ3JhZGllbnQlMjBtZXNoJTIwYmFja2dyb3VuZCUyMHN1YnRsZXxlbnwwfHx8Ymx1ZXwxNzgzODk3NzcyfDA&ixlib=rb-4.1.0&q=85",
        "category": "auth",
        "description": "Alternative mesh gradient for auth pages; use as decorative overlay only."
      }
    ],
    "texture_overlays": [
      {
        "url": "https://images.unsplash.com/photo-1650488908294-07186d808e5d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NDh8MHwxfHNlYXJjaHwxfHxzdWJ0bGUlMjBub2lzZSUyMHRleHR1cmUlMjBkYXJrJTIwYmFja2dyb3VuZHxlbnwwfHx8dGVhbHwxNzgzODk3Nzc2fDA&ixlib=rb-4.1.0&q=85",
        "category": "global",
        "description": "Use as inspiration for CSS noise overlay (do not load as full-screen image; recreate via CSS)."
      }
    ]
  },

  "typography": {
    "font_family": {
      "sans": "Inter, ui-sans-serif, system-ui",
      "mono": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace"
    },
    "scale_tailwind": {
      "h1": "text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight",
      "h2": "text-base md:text-lg font-medium text-muted-foreground",
      "section_title": "text-lg font-semibold",
      "card_title": "text-sm font-medium text-muted-foreground",
      "kpi_value": "text-2xl sm:text-3xl font-semibold tabular-nums",
      "body": "text-sm sm:text-base",
      "caption": "text-xs text-muted-foreground"
    },
    "numeric_rules": {
      "use_tabular_nums": true,
      "apply_to": ["kpis", "tables", "gauges", "timestamps", "percentages"]
    },
    "copy_tone": {
      "style": "concise, operator-friendly",
      "empty_state_formula": "What’s missing → Why it matters → How to fix (primary CTA)"
    }
  },

  "design_tokens": {
    "css_variables_location": "/app/frontend/src/index.css",
    "tokens": {
      "radius": {
        "--radius": "1rem",
        "--radius-sm": "0.75rem",
        "--radius-lg": "1.25rem"
      },
      "spacing": {
        "grid": "8px",
        "container_padding": "px-4 sm:px-6 lg:px-8",
        "section_gap": "gap-6 lg:gap-8",
        "card_padding": "p-4 sm:p-5"
      },
      "motion": {
        "durations_ms": {
          "fast": 120,
          "base": 180,
          "slow": 260,
          "live": 900
        },
        "easings": {
          "standard": "cubic-bezier(0.2, 0.8, 0.2, 1)",
          "emphasized": "cubic-bezier(0.2, 0.9, 0.1, 1)",
          "linear": "linear"
        }
      },
      "shadows": {
        "shadow-1": "0 1px 0 rgba(255,255,255,0.04), 0 10px 30px rgba(0,0,0,0.35)",
        "shadow-2": "0 1px 0 rgba(255,255,255,0.06), 0 18px 50px rgba(0,0,0,0.45)",
        "shadow-focus": "0 0 0 4px rgba(59,130,246,0.25)"
      }
    },
    "color_system": {
      "note": "Use provided palette as source of truth; implement as HSL tokens for shadcn compatibility.",
      "dark": {
        "background_hex": "#0B1220",
        "surface_hex": "#111827",
        "card_hex": "#1F2937",
        "primary_hex": "#3B82F6",
        "success_hex": "#22C55E",
        "warning_hex": "#F59E0B",
        "critical_hex": "#EF4444",
        "info_hex": "#06B6D4",
        "text_primary_hex": "#F9FAFB",
        "text_secondary_hex": "#9CA3AF",
        "offline_hex": "#6B7280",
        "border_alpha": "rgba(255,255,255,0.08)",
        "divider_alpha": "rgba(255,255,255,0.06)"
      },
      "light": {
        "background_hex": "#F8FAFC",
        "surface_hex": "#FFFFFF",
        "card_hex": "#FFFFFF",
        "primary_hex": "#2563EB",
        "success_hex": "#16A34A",
        "warning_hex": "#D97706",
        "critical_hex": "#DC2626",
        "info_hex": "#0891B2",
        "text_primary_hex": "#0F172A",
        "text_secondary_hex": "#475569",
        "offline_hex": "#64748B",
        "border_alpha": "rgba(15,23,42,0.10)",
        "divider_alpha": "rgba(15,23,42,0.08)"
      },
      "status_semantics": {
        "healthy": "#22C55E",
        "warning": "#F59E0B",
        "high_risk": "#F97316",
        "critical": "#EF4444",
        "offline": "#6B7280"
      },
      "chart_palette": {
        "series": ["#3B82F6", "#06B6D4", "#22C55E", "#F59E0B", "#F97316", "#EF4444"],
        "gridline_dark": "rgba(255,255,255,0.06)",
        "gridline_light": "rgba(15,23,42,0.08)"
      }
    },
    "tailwind_token_mapping": {
      "instruction": "Convert hex → HSL and set in :root and .dark. Keep shadcn variable names (background, foreground, card, popover, primary, secondary, muted, accent, destructive, border, input, ring). Add custom vars for surface, success, warning, critical, info, offline.",
      "additional_css_vars": [
        "--surface",
        "--surface-foreground",
        "--success",
        "--warning",
        "--critical",
        "--info",
        "--offline",
        "--border-subtle",
        "--shadow-1",
        "--shadow-2"
      ]
    }
  },

  "layout_and_grid": {
    "app_shell": {
      "structure": "Sidebar (collapsible) + Topbar (sticky) + Content",
      "sidebar": {
        "desktop_width": "w-[272px] (expanded), w-[76px] (collapsed)",
        "mobile": "Sheet drawer from left",
        "sections": [
          "Org switcher + collapse button",
          "Primary nav",
          "Secondary nav (Settings, Audit)",
          "Sidebar footer (agent status / websocket indicator)"
        ],
        "nav_item_height": "h-10",
        "active_state": "bg-white/6 border border-white/10 text-foreground",
        "hover_state": "bg-white/4"
      },
      "topbar": {
        "height": "h-14",
        "elements": [
          "Breadcrumbs",
          "Global search input",
          "Cmd+K hint",
          "Theme toggle",
          "Notifications",
          "User menu"
        ],
        "sticky": true,
        "background": "bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60",
        "border_bottom": "border-b border-white/10 (dark) or border-slate-900/10 (light)"
      },
      "content_container": {
        "max_width": "max-w-[1400px]",
        "padding": "px-4 sm:px-6 lg:px-8 py-6",
        "grid": "grid grid-cols-12 gap-4 lg:gap-6"
      }
    },
    "dashboard_page": {
      "top_row": "KPI cards (4–6) spanning 12 cols; on lg: each 3 cols",
      "middle": "Fleet health chart (8 cols) + Alerts panel (4 cols)",
      "bottom": "Activity feed (6 cols) + Top risky devices (6 cols)",
      "grouping": "Use section headers with small caps label + action (View all)."
    },
    "devices_grid_page": {
      "header": "Title + device count + filters + view toggle (grid/table)",
      "grid": "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4 lg:gap-6",
      "filters": "Use shadcn Select + Input + Badge chips; keep sticky filter bar on scroll for long lists."
    },
    "digital_twin_detail": {
      "header": "Device name + status dot + last seen + quick actions",
      "layout": "Two-column on lg: left (main tabs) 8 cols, right (side panels) 4 cols",
      "tabs": [
        "Overview",
        "Live Metrics",
        "Hardware",
        "Software",
        "Health Score",
        "AI Prediction (placeholder)",
        "Alerts",
        "Maintenance History",
        "Performance Charts",
        "Remote Actions"
      ],
      "sticky_subnav": "Tabs row can be sticky under topbar on desktop."
    },
    "auth_pages": {
      "layout": "Split-screen on lg: left brand panel (gradient band max 20% viewport height), right form card",
      "form_card": "Card with soft shadow, border, and clear hierarchy",
      "trust_elements": ["SOC2-ready copy placeholder", "Encryption note", "SSO coming soon (optional)"]
    }
  },

  "component_path": {
    "shadcn_ui": {
      "button": "/app/frontend/src/components/ui/button.jsx",
      "card": "/app/frontend/src/components/ui/card.jsx",
      "badge": "/app/frontend/src/components/ui/badge.jsx",
      "tabs": "/app/frontend/src/components/ui/tabs.jsx",
      "table": "/app/frontend/src/components/ui/table.jsx",
      "input": "/app/frontend/src/components/ui/input.jsx",
      "select": "/app/frontend/src/components/ui/select.jsx",
      "dropdown_menu": "/app/frontend/src/components/ui/dropdown-menu.jsx",
      "command_palette": "/app/frontend/src/components/ui/command.jsx",
      "dialog": "/app/frontend/src/components/ui/dialog.jsx",
      "alert_dialog": "/app/frontend/src/components/ui/alert-dialog.jsx",
      "sheet": "/app/frontend/src/components/ui/sheet.jsx",
      "breadcrumb": "/app/frontend/src/components/ui/breadcrumb.jsx",
      "skeleton": "/app/frontend/src/components/ui/skeleton.jsx",
      "sonner": "/app/frontend/src/components/ui/sonner.jsx",
      "switch": "/app/frontend/src/components/ui/switch.jsx",
      "progress": "/app/frontend/src/components/ui/progress.jsx",
      "scroll_area": "/app/frontend/src/components/ui/scroll-area.jsx",
      "separator": "/app/frontend/src/components/ui/separator.jsx",
      "tooltip": "/app/frontend/src/components/ui/tooltip.jsx",
      "calendar": "/app/frontend/src/components/ui/calendar.jsx",
      "pagination": "/app/frontend/src/components/ui/pagination.jsx"
    },
    "custom_components_to_create": {
      "StatBadge": "src/components/StatBadge.jsx",
      "KpiCard": "src/components/KpiCard.jsx",
      "DeviceCard": "src/components/DeviceCard.jsx",
      "HealthGauge": "src/components/HealthGauge.jsx",
      "EmptyState": "src/components/EmptyState.jsx",
      "TimeRangeSelector": "src/components/TimeRangeSelector.jsx",
      "LiveIndicator": "src/components/LiveIndicator.jsx",
      "DataTableToolbar": "src/components/DataTableToolbar.jsx",
      "RemoteActionButton": "src/components/RemoteActionButton.jsx"
    }
  },

  "component_recipes": {
    "Button": {
      "base": "rounded-xl h-10 px-4 text-sm font-medium inline-flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ring-offset-background",
      "variants": {
        "primary": "bg-primary text-primary-foreground shadow-[var(--shadow-1)] hover:bg-primary/90 active:scale-[0.98]",
        "secondary": "bg-secondary text-secondary-foreground border border-border hover:bg-secondary/80 active:scale-[0.98]",
        "ghost": "bg-transparent hover:bg-white/5 dark:hover:bg-white/5 hover:bg-slate-900/5",
        "destructive": "bg-[hsl(var(--critical))] text-white hover:opacity-90",
        "icon": "h-10 w-10 px-0"
      },
      "loading": {
        "pattern": "Replace left icon with spinner; keep label width stable.",
        "spinner": "lucide LoaderCircle with animate-spin"
      },
      "data_testid_examples": [
        "data-testid=\"login-form-submit-button\"",
        "data-testid=\"enrollment-code-copy-button\"",
        "data-testid=\"device-remote-restart-button\""
      ]
    },

    "Card": {
      "base": "rounded-2xl bg-card text-card-foreground border border-white/10 dark:border-white/10 border-slate-900/10 shadow-[var(--shadow-1)]",
      "interactive": "transition-colors duration-200 hover:border-white/15 hover:bg-white/[0.03]",
      "header": "p-4 sm:p-5 pb-2",
      "content": "p-4 sm:p-5 pt-3",
      "footer": "p-4 sm:p-5 pt-0"
    },

    "StatBadge": {
      "use_case": "Online/offline, severity, risk level, compliance",
      "base": "inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium border",
      "dot": "h-2 w-2 rounded-full",
      "variants": {
        "healthy": "bg-emerald-500/10 text-emerald-200 border-emerald-500/20",
        "warning": "bg-amber-500/10 text-amber-200 border-amber-500/20",
        "high-risk": "bg-orange-500/10 text-orange-200 border-orange-500/20",
        "critical": "bg-red-500/10 text-red-200 border-red-500/20",
        "offline": "bg-slate-500/10 text-slate-200 border-slate-500/20",
        "info": "bg-cyan-500/10 text-cyan-200 border-cyan-500/20"
      },
      "micro_interaction": "If status is online, dot pulses (animate-pulse) at low opacity; respect prefers-reduced-motion."
    },

    "KpiCard": {
      "layout": "Title row (label + info tooltip) → value (count-up) → delta + sparkline",
      "classes": {
        "wrapper": "rounded-2xl border border-white/10 bg-card shadow-[var(--shadow-1)] p-4 sm:p-5",
        "label": "text-xs font-medium text-muted-foreground",
        "value": "mt-2 text-3xl font-semibold tracking-tight tabular-nums",
        "meta": "mt-3 flex items-center justify-between text-xs text-muted-foreground"
      },
      "motion": {
        "enter": "Framer Motion: y: 8 → 0, opacity: 0 → 1, duration 0.26",
        "value": "Count-up on change; subtle highlight flash bg-primary/10 for 300ms"
      },
      "data_testid": {
        "value": "kpi-total-devices-value",
        "delta": "kpi-total-devices-delta"
      }
    },

    "DeviceCard": {
      "required_fields": [
        "device name",
        "online/offline indicator (pulsing dot)",
        "health score 0-100",
        "CPU %",
        "RAM %",
        "temperature",
        "network up/down",
        "last seen (relative)",
        "risk level badge"
      ],
      "layout": "Top: name + status badge + kebab menu. Middle: health gauge + key metrics grid. Bottom: last seen + quick action.",
      "classes": {
        "wrapper": "group rounded-2xl border border-white/10 bg-card p-4 sm:p-5 shadow-[var(--shadow-1)]",
        "hover": "transition-colors duration-200 hover:bg-white/[0.03] hover:border-white/15",
        "metrics_grid": "mt-4 grid grid-cols-2 gap-3",
        "metric": "rounded-xl bg-white/[0.03] border border-white/10 p-3",
        "metric_label": "text-[11px] text-muted-foreground",
        "metric_value": "mt-1 text-sm font-medium tabular-nums"
      },
      "micro_interactions": [
        "On hover: show subtle top highlight (pseudo-element) and raise shadow slightly",
        "Online dot: slow pulse (900ms)"
      ],
      "data_testid": {
        "card": "device-card",
        "status": "device-status-badge",
        "health": "device-health-score"
      }
    },

    "HealthGauge": {
      "type": "Radial gauge (SVG) or Recharts RadialBarChart",
      "display": "Score 0–100 + label (Healthy/Warning/High Risk/Critical)",
      "classes": {
        "wrapper": "relative flex items-center justify-center",
        "score": "absolute text-lg font-semibold tabular-nums",
        "label": "absolute mt-8 text-xs text-muted-foreground"
      },
      "color_logic": "Map score thresholds to status colors; keep consistent across app.",
      "data_testid": "health-gauge-score"
    },

    "EmptyState": {
      "layout": "Icon (lucide) → Title → Explanation → Primary CTA (+ optional secondary link)",
      "classes": {
        "wrapper": "rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-8 text-left",
        "icon": "h-10 w-10 text-muted-foreground",
        "title": "mt-4 text-base font-semibold",
        "desc": "mt-1 text-sm text-muted-foreground max-w-prose",
        "actions": "mt-6 flex flex-col sm:flex-row gap-3"
      },
      "empty_types": {
        "no_data": "No devices enrolled yet",
        "zero_results": "No devices match your filters",
        "error": "We couldn’t load devices"
      },
      "data_testid": {
        "wrapper": "empty-state",
        "primary_cta": "empty-state-primary-cta"
      }
    },

    "Tables": {
      "requirements": [
        "sticky headers",
        "sorting",
        "filtering",
        "pagination",
        "row hover",
        "empty state",
        "skeleton loading"
      ],
      "classes": {
        "table": "w-full",
        "thead": "sticky top-0 bg-background/80 backdrop-blur border-b border-white/10",
        "row": "hover:bg-white/[0.03]",
        "cell": "py-3",
        "header_cell": "text-xs font-medium text-muted-foreground"
      },
      "data_testid": {
        "table": "devices-table",
        "row": "devices-table-row",
        "pagination_next": "table-pagination-next"
      }
    },

    "EnrollmentModal": {
      "component": "Dialog",
      "glassmorphism": {
        "panel": "bg-background/60 backdrop-blur-xl border border-white/15 shadow-[var(--shadow-2)]",
        "note": "Only here and other dialogs/sheets."
      },
      "content": [
        "Enrollment code",
        "QR",
        "Expiry countdown",
        "Copy button",
        "Regenerate button",
        "Security note"
      ],
      "data_testid": {
        "open": "open-enrollment-modal-button",
        "code": "enrollment-code-value",
        "copy": "enrollment-code-copy-button"
      }
    },

    "CommandPalette": {
      "component": "Command",
      "trigger": "Ctrl/Cmd + K",
      "groups": ["Navigate", "Devices", "Alerts", "Actions"],
      "row": "h-11",
      "data_testid": {
        "open": "command-palette-open",
        "input": "command-palette-input",
        "item": "command-palette-item"
      }
    }
  },

  "charts_recharts": {
    "principles": [
      "Prefer fewer lines with clear legend; avoid rainbow overload.",
      "Use subtle gridlines and strong tooltip contrast.",
      "Animate on mount and on time-range change; avoid constant re-animating on every websocket tick."
    ],
    "time_range_selector": {
      "ranges": ["1h", "6h", "24h", "7d"],
      "ui": "ToggleGroup or segmented Buttons",
      "data_testid": "time-range-selector"
    },
    "live_updates": {
      "pattern": "Append points; keep domain stable; show LiveIndicator dot in chart header.",
      "empty_state": "Show skeleton chart frame + message 'Waiting for telemetry…'"
    },
    "tooltip": {
      "style": "bg-popover text-popover-foreground border border-white/10 rounded-xl shadow-[var(--shadow-2)]",
      "content": "Use mono for timestamps and tabular nums for values."
    },
    "zoom": {
      "note": "If implementing zoom, use Recharts Brush for time window selection; keep it optional and hidden on mobile."
    }
  },

  "motion_and_micro_interactions": {
    "principles": [
      "Motion communicates state: live, loading, success, warning.",
      "No universal transitions; only transition-colors/opacity/shadow.",
      "Respect prefers-reduced-motion."
    ],
    "patterns": {
      "hover": "Cards: transition-colors duration-200; Buttons: active scale 0.98",
      "loading": "Skeleton shimmer for panels; spinner for button actions",
      "live": "Online dot pulse; subtle highlight flash on updated KPI",
      "route_change": "Framer Motion page fade/slide (opacity + y)"
    }
  },

  "accessibility": {
    "wcag": "AA",
    "focus": "Always visible focus ring using ring + ring-offset",
    "keyboard": [
      "Cmd/Ctrl+K opens command palette",
      "Esc closes dialogs/sheets",
      "Tab order follows visual order",
      "Tables: sortable headers are buttons"
    ],
    "color": "Never rely on color alone for severity; pair with icon/label.",
    "reduced_motion": "Disable pulses and count-up when prefers-reduced-motion is enabled."
  },

  "instructions_to_main_agent": {
    "high_priority": [
      "Replace CRA default App.css centering patterns; do not use .App { text-align:center }.",
      "Update index.css tokens to match provided palette (dark default) using shadcn variable names + custom semantic vars.",
      "Implement AppShell with collapsible sidebar + sticky topbar; mobile sidebar uses Sheet.",
      "Use shadcn Command for command palette; wire Ctrl/Cmd+K.",
      "Use sonner for toasts (top-right).",
      "No mock data: implement EmptyState component and use it everywhere data can be empty.",
      "All interactive/key info elements must include data-testid attributes (kebab-case).",
      "Charts: Recharts with smooth animations; add time range selector; live updates via WebSocket without re-animating entire chart each tick.",
      "Glassmorphism ONLY for Dialog/Sheet surfaces."
    ],
    "implementation_notes_js": [
      "Project uses .jsx components; keep examples and component scaffolds in .jsx.",
      "Prefer named exports for components; default exports for pages."
    ]
  },

  "gradient_restriction_rule": {
    "prohibited": [
      "blue-500 to purple-600",
      "purple-500 to pink-500",
      "green-500 to blue-500",
      "red to pink"
    ],
    "constraints": {
      "max_viewport_coverage": "20%",
      "no_text_heavy_areas": true,
      "no_small_elements_under_100px": true,
      "no_stacked_gradients": true
    },
    "allowed_usage": [
      "Hero/auth header band backgrounds only",
      "Decorative overlays/accent shapes",
      "Large section backgrounds (subtle)"
    ],
    "recommended_gradients": [
      {
        "name": "Arctic Blue Band",
        "css": "linear-gradient(135deg, rgba(59,130,246,0.35), rgba(6,182,212,0.18), rgba(11,18,32,0))",
        "usage": "Auth header band / dashboard header strip"
      }
    ]
  },

  "appendix_general_ui_ux_design_guidelines": "<General UI UX Design Guidelines>  \n    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.\n</General UI UX Design Guidelines>"
}
