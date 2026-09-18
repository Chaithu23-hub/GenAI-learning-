The contract-repository server is maintained by the knowledge-team repository service, not by this assistant.
It can reach contract identifiers, executed effective dates, amendment chains, and read-only repository metadata.
It logs tool requests and returned contract identifiers for audit purposes; the host does not send model prompts to it.
A stolen access token could expose executed contract metadata and amendment history within its permission scope.
Ship only with read-only credentials, allowlisted server commands, and audit review; do not ship an unrestricted token.
