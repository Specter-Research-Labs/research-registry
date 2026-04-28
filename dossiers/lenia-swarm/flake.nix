{
  description = "lenia-swarm dev shell";

  outputs = { self }:
    let
      system = "aarch64-darwin";
      shells = import ../../ops/nix/shells.nix { inherit system; };
    in
    {
      devShells.${system}.default = shells.mkProjectShell {
        pythonVersion = "3.11";
        bootstrap = {
          uvSync = true;
          swiftResolve = true;
        };
      };
    };
}
