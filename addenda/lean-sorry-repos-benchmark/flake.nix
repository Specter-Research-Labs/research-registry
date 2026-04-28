{
  description = "lean-sorry-repos-benchmark dev shell";

  outputs = { self }:
    let
      system = "aarch64-darwin";
      shells = import ../../ops/nix/shells.nix { inherit system; };
    in
    {
      devShells.${system}.default = shells.mkPythonProjectShell {
        pythonVersion = "3.12";
      };
    };
}
