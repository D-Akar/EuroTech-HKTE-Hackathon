// three's example loaders ship without bundled types in this version.
declare module "three/examples/jsm/loaders/DRACOLoader.js" {
  import { Loader, LoadingManager } from "three";
  export class DRACOLoader extends Loader {
    constructor(manager?: LoadingManager);
    setDecoderPath(path: string): this;
    setDecoderConfig(config: object): this;
    setWorkerLimit(workerLimit: number): this;
    preload(): this;
    dispose(): this;
  }
}
