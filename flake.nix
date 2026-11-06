{
  description = "Specter Labs root dev shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          shells = import ./ops/nix/shells.nix { inherit system pkgs; };
        in
        {
          default = shells.mkRootShell;
          "poly-morphogenesis" = shells.mkPolyMorphogenesisShell;
        });
    };
}
