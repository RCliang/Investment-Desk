import { Component, PropsWithChildren } from 'react'
import { initCloud } from './services/cloud'
import './app.scss'

class App extends Component<PropsWithChildren> {
  componentDidMount() {
    initCloud()
  }

  componentDidShow() {}

  componentDidHide() {}

  render() {
    return this.props.children
  }
}

export default App
