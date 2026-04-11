"""Sorta.Fit adapters -- board integrations."""

# Registry mapping adapter name to (module_path, class_name) for lazy loading.
# Pro modules can extend this dict to register additional adapters.
ADAPTER_REGISTRY: dict[str, tuple[str, str]] = {
    "jira": ("sortafit.adapters.jira", "JiraAdapter"),
    "linear": ("sortafit.adapters.linear", "LinearAdapter"),
    "github-issues": ("sortafit.adapters.github_issues", "GitHubIssuesAdapter"),
}

__all__ = ["ADAPTER_REGISTRY"]
