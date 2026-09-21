"""
The Candidate layer: the boundary between immutable evidence and future canonical truth.

    Observation -> ProcessingAttempt -> [proposer] -> Candidate -> (future validation/resolution/promotion)

  proposer.py   the CandidateProposer port (pure: no repositories, database, network or AI SDK)
  evidence.py   deterministic evidence verification (pure)
  service.py    orchestration: persist verified candidates for a PROCESSING attempt

Nothing here can create canonical state, and nothing here may import a future
resolution/promotion package (enforced by the architecture tests).
"""
