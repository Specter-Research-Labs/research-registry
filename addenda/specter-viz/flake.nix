{
  description = "specter-viz dev shell";

  outputs = { self }:
    let
      system = "aarch64-darwin";
      shells = import ../../ops/nix/shells.nix { inherit system; };
    in
    {
      devShells.${system}.default = shells.mkRustProjectShell { };
    };
}
