{
  description = "Specter Labs root dev shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "aarch64-darwin";
      pkgs = import nixpkgs { inherit system; };
      shells = import ./ops/nix/shells.nix { inherit system pkgs; };
    in
    {
      devShells.${system}.default = shells.mkRootShell;
    };
}
